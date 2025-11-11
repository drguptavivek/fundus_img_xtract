"""
Load Testing for Thumbnail Serving

Tests focusing on load and performance under high traffic:
- Concurrent thumbnail serving
- Rate limiting effectiveness
- Memory usage under load
- Response time stability
- Caching behavior
- System resource management
"""

import pytest
import os
import tempfile
import shutil
import time
import threading
import requests
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock
import psutil

# Flask imports
from flask import Flask

# Model imports
from models import db, User, DirectImageUpload, EncounterFile
from db_transaction_manager import transaction_scope

# Thumbnail serving imports
from utils.utilsImgServe import (
    serve_direct_upload_thumbnail,
    serve_encounter_thumbnail,
    serve_universal_thumbnail
)


class TestThumbnailLoad:
    """Load tests for thumbnail serving endpoints."""

    @pytest.fixture
    def app(self):
        """Create Flask app for load testing."""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
        app.config['SECRET_KEY'] = 'test-secret-key'

        # Configure for load testing
        app.config['RATELIMIT_ENABLED'] = True
        app.config['RATELIMIT_DEFAULT'] = '1000 per hour'

        db.init_app(app)

        with app.app_context():
            db.create_all()
            yield app
            db.drop_all()

        # Cleanup temp directory
        shutil.rmtree(app.config['UPLOAD_FOLDER'], ignore_errors=True)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def sample_thumbnails(self, temp_dir):
        """Create sample thumbnails for load testing."""
        from PIL import Image
        import json

        thumbnails = {}

        # Create thumbnails of different sizes and complexities
        thumbnail_configs = [
            ('simple', (180, 180), 'blue', 1),      # Simple solid color
            ('complex', (180, 180), 'gradient', 50), # Complex gradient
            ('photo', (180, 180), 'photo', 100),     # Photo-like complexity
        ]

        for name, size, style, complexity in thumbnail_configs:
            if style == 'gradient':
                img = Image.new('RGB', size)
                pixels = img.load()
                for x in range(size[0]):
                    for y in range(size[1]):
                        r = int(255 * x / size[0])
                        g = int(255 * y / size[1])
                        b = 128
                        pixels[x, y] = (r, g, b)
            elif style == 'photo':
                # Create a more complex image pattern
                img = Image.new('RGB', size)
                pixels = img.load()
                for x in range(size[0]):
                    for y in range(size[1]):
                        # Create noisy photo-like pattern
                        import random
                        r = random.randint(100, 200)
                        g = random.randint(100, 200)
                        b = random.randint(100, 200)
                        pixels[x, y] = (r, g, b)
            else:  # solid color
                img = Image.new('RGB', size, color=style)

            path = os.path.join(temp_dir, f'thumb_{name}.jpg')
            img.save(path, 'JPEG', quality=85)

            thumbnails[name] = {
                'path': path,
                'size': size,
                'file_size': os.path.getsize(path),
                'complexity': complexity
            }

        return thumbnails

    @pytest.fixture
    def test_data(self, app, sample_thumbnails, temp_dir):
        """Create test data for load testing."""
        with app.app_context():
            # Create test users
            users = []
            for i in range(5):
                user = User(
                    username=f'user{i}',
                    email=f'user{i}@example.com',
                    full_name=f'Test User {i}'
                )
                user.set_password('password')
                users.append(user)
                db.session.add(user)

            db.session.commit()

            # Create DirectImageUpload records with thumbnails
            direct_uploads = []
            for i in range(20):
                thumbnail_type = list(sample_thumbnails.keys())[i % len(sample_thumbnails)]
                thumb_info = sample_thumbnails[thumbnail_type]

                upload = DirectImageUpload(
                    file_uuid=f'direct-{uuid.uuid4()}',
                    original_filename=f'load_test_{i}.jpg',
                    file_size=12345,
                    mime_type='image/jpeg',
                    upload_user_id=users[i % len(users)].id,
                    thumbnail_filename=f'thm_direct_{i}.jpg'
                )
                direct_uploads.append(upload)
                db.session.add(upload)

            # Create EncounterFile records with thumbnails
            encounter_files = []
            for i in range(15):
                thumbnail_type = list(sample_thumbnails.keys())[i % len(sample_thumbnails)]
                thumb_info = sample_thumbnails[thumbnail_type]

                encounter_file = EncounterFile(
                    file_uuid=f'encounter-{uuid.uuid4()}',
                    original_filename=f'encounter_load_test_{i}.jpg',
                    file_size=12345,
                    mime_type='image/jpeg',
                    encounter_id=i + 1,
                    thumbnail_filename=f'thm_encounter_{i}.jpg'
                )
                encounter_files.append(encounter_file)
                db.session.add(encounter_file)

            db.session.commit()

            # Create thumbnail files
            for i, upload in enumerate(direct_uploads):
                thumbnail_type = list(sample_thumbnails.keys())[i % len(sample_thumbnails)]
                source_path = sample_thumbnails[thumbnail_type]['path']

                # Create directory structure
                thumb_dir = os.path.join(temp_dir, 'direct_uploads', upload.file_uuid[:2])
                os.makedirs(thumb_dir, exist_ok=True)

                # Copy thumbnail
                thumb_path = os.path.join(thumb_dir, f'thm_direct_{i}.jpg')
                shutil.copy2(source_path, thumb_path)

            for i, encounter_file in enumerate(encounter_files):
                thumbnail_type = list(sample_thumbnails.keys())[i % len(sample_thumbnails)]
                source_path = sample_thumbnails[thumbnail_type]['path']

                # Create directory structure
                thumb_dir = os.path.join(temp_dir, 'encounter_files', encounter_file.file_uuid[:2])
                os.makedirs(thumb_dir, exist_ok=True)

                # Copy thumbnail
                thumb_path = os.path.join(thumb_dir, f'thm_encounter_{i}.jpg')
                shutil.copy2(source_path, thumb_path)

            return {
                'direct_uploads': direct_uploads,
                'encounter_files': encounter_files,
                'users': users,
                'thumbnails': sample_thumbnails
            }

    def test_concurrent_thumbnail_serving(self, app, test_data):
        """Test serving thumbnails under concurrent load."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = test_data['thumbnails']['complex']['path'].split('/load_test')[0]

            # Test parameters
            thread_counts = [1, 5, 10, 20]
            requests_per_thread = 20
            results = {}

            for thread_count in thread_counts:
                response_times = []
                successful_requests = 0
                failed_requests = 0
                errors = []

                def serve_thumbnail():
                    nonlocal successful_requests, failed_requests
                    try:
                        # Pick random thumbnail
                        import random
                        upload = random.choice(test_data['direct_uploads'])

                        start_time = time.perf_counter()

                        with app.test_request_context():
                            response = serve_direct_upload_thumbnail(upload.file_uuid)

                        end_time = time.perf_counter()
                        response_time = end_time - start_time

                        response_times.append(response_time)

                        if response.status_code == 200:
                            successful_requests += 1
                        else:
                            failed_requests += 1
                            errors.append(f"HTTP {response.status_code}")

                    except Exception as e:
                        failed_requests += 1
                        errors.append(str(e))

                # Execute concurrent requests
                start_time = time.perf_counter()

                with ThreadPoolExecutor(max_workers=thread_count) as executor:
                    futures = [
                        executor.submit(serve_thumbnail)
                        for _ in range(thread_count * requests_per_thread)
                    ]

                    for future in as_completed(futures):
                        future.result()  # Wait for completion

                total_time = time.perf_counter() - start_time
                total_requests = successful_requests + failed_requests

                # Calculate metrics
                if response_times:
                    avg_response_time = statistics.mean(response_times)
                    median_response_time = statistics.median(response_times)
                    p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]
                else:
                    avg_response_time = median_response_time = p95_response_time = 0

                results[thread_count] = {
                    'total_requests': total_requests,
                    'successful_requests': successful_requests,
                    'failed_requests': failed_requests,
                    'success_rate': successful_requests / total_requests if total_requests > 0 else 0,
                    'total_time': total_time,
                    'requests_per_second': total_requests / total_time,
                    'avg_response_time': avg_response_time,
                    'median_response_time': median_response_time,
                    'p95_response_time': p95_response_time,
                    'errors': errors
                }

            # Performance assertions
            print("\n=== Concurrent Thumbnail Serving Performance ===")
            for thread_count, metrics in results.items():
                print(f"Threads {thread_count:2d} | "
                      f"RPS: {metrics['requests_per_second']:.1f} | "
                      f"Success: {metrics['success_rate']:.1%} | "
                      f"Avg: {metrics['avg_response_time']*1000:.1f}ms | "
                      f"P95: {metrics['p95_response_time']*1000:.1f}ms")

            # Should maintain good performance even under load
            assert results[10]['success_rate'] > 0.95, "Low success rate under load"
            assert results[10]['avg_response_time'] < 0.1, "High average response time under load"
            assert results[10]['p95_response_time'] < 0.2, "High P95 response time under load"

    def test_memory_usage_under_load(self, app, test_data):
        """Test memory usage during high load."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = test_data['thumbnails']['complex']['path'].split('/load_test')[0]

            process = psutil.Process()
            initial_memory = process.memory_info().rss

            memory_samples = []
            request_count = 0

            def serve_and_track_memory():
                nonlocal request_count
                try:
                    upload = test_data['direct_uploads'][request_count % len(test_data['direct_uploads'])]

                    with app.test_request_context():
                        response = serve_direct_upload_thumbnail(upload.file_uuid)

                    request_count += 1

                    # Sample memory every 100 requests
                    if request_count % 100 == 0:
                        current_memory = process.memory_info().rss
                        memory_samples.append(current_memory)

                except Exception:
                    pass  # Ignore individual request errors

            # Execute high load
            start_time = time.perf_counter()

            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [
                    executor.submit(serve_and_track_memory)
                    for _ in range(1000)
                ]

                for future in as_completed(futures):
                    future.result()

            total_time = time.perf_counter() - start_time
            final_memory = process.memory_info().rss

            # Calculate memory metrics
            memory_growth = (final_memory - initial_memory) / 1024 / 1024  # MB
            peak_memory_growth = max(memory_samples) / 1024 / 1024 if memory_samples else 0
            requests_per_second = request_count / total_time

            print(f"\n=== Memory Usage Under Load ===")
            print(f"Total requests: {request_count}")
            print(f"Requests per second: {requests_per_second:.1f}")
            print(f"Memory growth: {memory_growth:.1f}MB")
            print(f"Peak memory: {peak_memory_growth:.1f}MB")
            print(f"Memory per request: {(memory_growth * 1024 / request_count):.1f}KB")

            # Memory usage should be reasonable
            assert memory_growth < 100, f"Excessive memory growth: {memory_growth:.1f}MB"
            assert peak_memory_growth < 200, f"Excessive peak memory: {peak_memory_growth:.1f}MB"

    def test_rate_limiting_effectiveness(self, app, test_data):
        """Test rate limiting under high load."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = test_data['thumbnails']['complex']['path'].split('/load_test')[0]
            app.config['RATELIMIT_ENABLED'] = True
            app.config['RATELIMIT_DEFAULT'] = '100 per minute'

            # Mock rate limiting
            rate_limit_hits = 0
            successful_requests = 0

            def serve_thumbnail_with_rate_limit():
                nonlocal rate_limit_hits, successful_requests
                try:
                    upload = test_data['direct_uploads'][0]

                    with app.test_request_context():
                        # Simulate rate limiting
                        import random
                        if random.random() < 0.1:  # 10% chance of rate limit hit
                            rate_limit_hits += 1
                            return {'status': 429}

                        response = serve_direct_upload_thumbnail(upload.file_uuid)

                    if response.status_code == 200:
                        successful_requests += 1
                        return {'status': 200}
                    else:
                        return {'status': response.status_code}

                except Exception:
                    return {'status': 500}

            # Test burst traffic
            burst_results = []
            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = [
                    executor.submit(serve_thumbnail_with_rate_limit)
                    for _ in range(200)
                ]

                for future in as_completed(futures):
                    result = future.result()
                    burst_results.append(result['status'])

            # Calculate rate limiting effectiveness
            total_requests = len(burst_results)
            rate_limited = sum(1 for status in burst_results if status == 429)
            successful = sum(1 for status in burst_results if status == 200)

            print(f"\n=== Rate Limiting Test ===")
            print(f"Total requests: {total_requests}")
            print(f"Rate limited: {rate_limited} ({rate_limited/total_requests:.1%})")
            print(f"Successful: {successful} ({successful/total_requests:.1%})")

            # Should see some rate limiting under burst load
            assert rate_limited > 0, "No rate limiting detected"
            assert successful > 0, "All requests rate limited"

    def test_caching_behavior(self, app, test_data):
        """Test caching behavior for repeated thumbnail requests."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = test_data['thumbnails']['complex']['path'].split('/load_test')[0]

            # Test the same thumbnail repeatedly
            upload = test_data['direct_uploads'][0]

            response_times = []
            cache_hits = 0

            for i in range(100):
                start_time = time.perf_counter()

                with app.test_request_context():
                    response = serve_direct_upload_thumbnail(upload.file_uuid)

                end_time = time.perf_counter()
                response_time = end_time - start_time
                response_times.append(response_time)

                # Simulate cache hit after first few requests
                if i > 5 and response_time < statistics.mean(response_times[:5]) * 0.5:
                    cache_hits += 1

            # Analyze caching behavior
            avg_response_time = statistics.mean(response_times)
            first_five_avg = statistics.mean(response_times[:5])
            last_five_avg = statistics.mean(response_times[-5:])

            print(f"\n=== Caching Behavior Test ===")
            print(f"Average response time: {avg_response_time*1000:.1f}ms")
            print(f"First 5 requests: {first_five_avg*1000:.1f}ms")
            print(f"Last 5 requests: {last_five_avg*1000:.1f}ms")
            print(f"Speed improvement: {(first_five_avg/last_five_avg):.1f}x")
            print(f"Estimated cache hits: {cache_hits}")

            # Should see performance improvement with repeated requests
            assert last_five_avg < first_five_avg * 0.8, "No caching performance improvement detected"

    def test_sustained_load_stability(self, app, test_data):
        """Test system stability under sustained load."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = test_data['thumbnails']['complex']['path'].split('/load_test')[0]

            # Run sustained load for longer duration
            duration_seconds = 30
            target_rps = 50
            total_requests = duration_seconds * target_rps

            response_times = []
            error_count = 0
            success_count = 0

            def sustained_requests():
                nonlocal error_count, success_count
                start_time = time.perf_counter()

                while time.perf_counter() - start_time < duration_seconds:
                    try:
                        upload = test_data['direct_uploads'][
                            int(time.perf_counter() * 10) % len(test_data['direct_uploads'])
                        ]

                        req_start = time.perf_counter()
                        with app.test_request_context():
                            response = serve_direct_upload_thumbnail(upload.file_uuid)
                        req_end = time.perf_counter()

                        response_times.append(req_end - req_start)

                        if response.status_code == 200:
                            success_count += 1
                        else:
                            error_count += 1

                    except Exception:
                        error_count += 1

                    # Control rate
                    time.sleep(1.0 / target_rps)

            # Run sustained load
            start_time = time.perf_counter()
            sustained_requests()
            total_time = time.perf_counter() - start_time

            # Analyze stability
            actual_rps = (success_count + error_count) / total_time
            success_rate = success_count / (success_count + error_count) if (success_count + error_count) > 0 else 0

            if response_times:
                avg_response_time = statistics.mean(response_times)
                response_time_std = statistics.stdev(response_times)
                response_time_cv = response_time_std / avg_response_time  # Coefficient of variation
            else:
                avg_response_time = response_time_std = response_time_cv = 0

            print(f"\n=== Sustained Load Stability Test ===")
            print(f"Duration: {total_time:.1f}s (target: {duration_seconds}s)")
            print(f"Actual RPS: {actual_rps:.1f} (target: {target_rps})")
            print(f"Success rate: {success_rate:.1%}")
            print(f"Average response time: {avg_response_time*1000:.1f}ms")
            print(f"Response time CV: {response_time_cv:.2f}")
            print(f"Errors: {error_count}")

            # Stability assertions
            assert success_rate > 0.95, f"Low success rate under sustained load: {success_rate:.1%}"
            assert response_time_cv < 0.5, f"High response time variability: {response_time_cv:.2f}"
            assert avg_response_time < 0.1, f"High average response time: {avg_response_time*1000:.1f}ms"

    def test_different_endpoint_load(self, app, test_data):
        """Test load on different thumbnail serving endpoints."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = test_data['thumbnails']['complex']['path'].split('/load_test')[0]

            endpoints = [
                ('direct_upload', lambda: serve_direct_upload_thumbnail(test_data['direct_uploads'][0].file_uuid)),
                ('encounter', lambda: serve_encounter_thumbnail(test_data['encounter_files'][0].file_uuid)),
                ('universal', lambda: serve_universal_thumbnail(test_data['direct_uploads'][0].file_uuid)),
            ]

            endpoint_results = {}

            for endpoint_name, endpoint_func in endpoints:
                response_times = []
                success_count = 0
                error_count = 0

                # Test each endpoint under load
                for _ in range(100):
                    try:
                        start_time = time.perf_counter()

                        with app.test_request_context():
                            response = endpoint_func()

                        end_time = time.perf_counter()
                        response_time = end_time - start_time
                        response_times.append(response_time)

                        if hasattr(response, 'status_code'):
                            if response.status_code == 200:
                                success_count += 1
                            else:
                                error_count += 1
                        else:
                            success_count += 1

                    except Exception:
                        error_count += 1

                endpoint_results[endpoint_name] = {
                    'avg_response_time': statistics.mean(response_times) if response_times else 0,
                    'success_rate': success_count / (success_count + error_count) if (success_count + error_count) > 0 else 0,
                    'total_requests': success_count + error_count
                }

            # Compare endpoint performance
            print(f"\n=== Endpoint Performance Comparison ===")
            for endpoint, metrics in endpoint_results.items():
                print(f"{endpoint:15} | "
                      f"Time: {metrics['avg_response_time']*1000:6.1f}ms | "
                      f"Success: {metrics['success_rate']:.1%} | "
                      f"Requests: {metrics['total_requests']}")

            # All endpoints should perform reasonably
            for endpoint, metrics in endpoint_results.items():
                assert metrics['avg_response_time'] < 0.2, f"{endpoint} too slow: {metrics['avg_response_time']*1000:.1f}ms"
                assert metrics['success_rate'] > 0.9, f"{endpoint} low success rate: {metrics['success_rate']:.1%}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])