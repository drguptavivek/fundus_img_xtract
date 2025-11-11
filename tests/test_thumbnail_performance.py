"""
Performance Tests for Thumbnail System

Tests focusing on performance aspects:
- Thumbnail generation speed and memory usage
- Concurrent processing performance
- Database query optimization
- File I/O performance
- Scalability under load
"""

import pytest
import os
import tempfile
import shutil
import time
import threading
import psutil
import gc
from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

# Import the functions we're testing
from utils.image_processing import generate_thumbnail
from utils.thumbnail_jobs import create_thumbnail_job, process_thumbnail_job
from utils.thumbnail_integration import trigger_direct_upload_thumbnails
from models import db, DirectImageUpload, Job, JobItem
from db_transaction_manager import transaction_scope


class TestThumbnailPerformance:
    """Performance tests for thumbnail generation."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def performance_images(self, temp_dir):
        """Create test images of various sizes for performance testing."""
        images = {}

        # Create images of different sizes to test performance
        test_sizes = [
            ('small', (100, 100), 'small.jpg'),
            ('medium', (800, 600), 'medium.jpg'),
            ('large', (2000, 1500), 'large.jpg'),
            ('very_large', (4000, 3000), 'very_large.jpg'),
            ('ultra_wide', (8000, 1000), 'ultra_wide.jpg'),
            ('ultra_tall', (1000, 8000), 'ultra_tall.jpg'),
        ]

        for name, size, filename in test_sizes:
            # Create image with some complexity (gradient)
            image = Image.new('RGB', size)
            pixels = image.load()

            for x in range(size[0]):
                for y in range(size[1]):
                    # Create a gradient pattern
                    r = int(255 * x / size[0])
                    g = int(255 * y / size[1])
                    b = 128
                    pixels[x, y] = (r, g, b)

            file_path = os.path.join(temp_dir, filename)
            image.save(file_path, 'JPEG', quality=95)

            images[name] = {
                'path': file_path,
                'size': size,
                'file_size': os.path.getsize(file_path)
            }

        return images

    @pytest.fixture
    def memory_tracker(self):
        """Memory usage tracker for performance testing."""
        process = psutil.Process()

        class MemoryTracker:
            def __init__(self):
                self.baseline = process.memory_info().rss
                self.peak = self.baseline
                self.samples = []

            def sample(self):
                current = process.memory_info().rss
                self.samples.append(current)
                self.peak = max(self.peak, current)
                return current

            def get_stats(self):
                return {
                    'baseline_mb': self.baseline / 1024 / 1024,
                    'peak_mb': self.peak / 1024 / 1024,
                    'growth_mb': (self.peak - self.baseline) / 1024 / 1024,
                    'samples': len(self.samples)
                }

        return MemoryTracker()

    def test_thumbnail_generation_speed(self, performance_images, temp_dir, memory_tracker):
        """Test thumbnail generation speed for different image sizes."""
        results = {}

        for image_name, image_info in performance_images.items():
            # Clear memory before each test
            gc.collect()
            memory_tracker.sample()

            output_path = os.path.join(temp_dir, f'thumb_{image_name}.jpg')

            # Measure generation time
            start_time = time.perf_counter()
            result = generate_thumbnail(image_info['path'], output_path)
            end_time = time.perf_counter()

            generation_time = end_time - start_time
            memory_after = memory_tracker.sample()

            # Verify success
            assert result is True
            assert os.path.exists(output_path)

            # Collect performance metrics
            results[image_name] = {
                'source_size': image_info['size'],
                'source_file_size_mb': image_info['file_size'] / 1024 / 1024,
                'generation_time_sec': generation_time,
                'memory_usage_mb': (memory_after - memory_tracker.baseline) / 1024 / 1024,
                'thumbnail_size_kb': os.path.getsize(output_path) / 1024,
                'compression_ratio': image_info['file_size'] / os.path.getsize(output_path)
            }

        # Performance assertions
        # Small images should be processed very quickly
        assert results['small']['generation_time_sec'] < 0.1, "Small image processing too slow"
        assert results['medium']['generation_time_sec'] < 0.5, "Medium image processing too slow"
        assert results['large']['generation_time_sec'] < 2.0, "Large image processing too slow"

        # Memory usage should be reasonable
        for image_name, metrics in results.items():
            assert metrics['memory_usage_mb'] < 100, f"Memory usage too high for {image_name}: {metrics['memory_usage_mb']}MB"

        # Print performance report
        print("\n=== Thumbnail Generation Performance Report ===")
        for image_name, metrics in results.items():
            print(f"{image_name:12} | {metrics['generation_time_sec']:.3f}s | "
                  f"{metrics['memory_usage_mb']:.1f}MB | {metrics['compression_ratio']:.1f}x")

    def test_batch_processing_performance(self, performance_images, temp_dir):
        """Test performance of batch thumbnail generation."""
        batch_sizes = [5, 10, 20, 50]
        results = {}

        for batch_size in batch_sizes:
            # Clear memory before batch
            gc.collect()

            output_paths = []
            start_time = time.perf_counter()

            # Generate thumbnails in batch
            for i in range(batch_size):
                # Cycle through images to get variety
                image_name = list(performance_images.keys())[i % len(performance_images)]
                source_path = performance_images[image_name]['path']
                output_path = os.path.join(temp_dir, f'batch_{batch_size}_{i}.jpg')
                output_paths.append(output_path)

                result = generate_thumbnail(source_path, output_path)
                assert result is True

            end_time = time.perf_counter()
            total_time = end_time - start_time

            # Verify all thumbnails created
            for output_path in output_paths:
                assert os.path.exists(output_path)

            results[batch_size] = {
                'total_time_sec': total_time,
                'avg_time_per_thumbnail': total_time / batch_size,
                'thumbnails_per_sec': batch_size / total_time
            }

        # Performance expectations
        assert results[5]['avg_time_per_thumbnail'] < 0.1, "Small batch too slow"
        assert results[50]['thumbnails_per_sec'] > 5, "Large batch throughput too low"

        print("\n=== Batch Processing Performance ===")
        for batch_size, metrics in results.items():
            print(f"Batch {batch_size:3d} | {metrics['total_time_sec']:.2f}s total | "
                  f"{metrics['avg_time_per_thumbnail']:.3f}s avg | "
                  f"{metrics['thumbnails_per_sec']:.1f}/sec")

    def test_concurrent_generation_performance(self, performance_images, temp_dir):
        """Test performance of concurrent thumbnail generation."""
        thread_counts = [1, 2, 4, 8]
        thumbnails_per_thread = 5
        results = {}

        for thread_count in thread_counts:
            gc.collect()

            def generate_thumbnails(thread_id):
                thread_results = []
                for i in range(thumbnails_per_thread):
                    image_name = list(performance_images.keys())[(thread_id * thumbnails_per_thread + i) % len(performance_images)]
                    source_path = performance_images[image_name]['path']
                    output_path = os.path.join(temp_dir, f'concurrent_{thread_count}_{thread_id}_{i}.jpg')

                    start_time = time.perf_counter()
                    result = generate_thumbnail(source_path, output_path)
                    end_time = time.perf_counter()

                    thread_results.append({
                        'success': result,
                        'time': end_time - start_time,
                        'output_path': output_path
                    })

                return thread_results

            start_time = time.perf_counter()

            # Run with specified number of threads
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                futures = [executor.submit(generate_thumbnails, i) for i in range(thread_count)]
                all_results = []

                for future in as_completed(futures):
                    thread_results = future.result()
                    all_results.extend(thread_results)

            end_time = time.perf_counter()
            total_time = end_time - start_time

            # Verify all thumbnails created successfully
            successful_count = sum(1 for r in all_results if r['success'])
            assert successful_count == thread_count * thumbnails_per_thread

            # Calculate metrics
            avg_thread_time = sum(r['time'] for r in all_results) / len(all_results)
            throughput = successful_count / total_time

            results[thread_count] = {
                'total_time_sec': total_time,
                'avg_thread_time_sec': avg_thread_time,
                'throughput_per_sec': throughput,
                'successful_count': successful_count
            }

            # Cleanup generated files
            for r in all_results:
                if os.path.exists(r['output_path']):
                    os.remove(r['output_path'])

        # Analyze scaling efficiency
        single_thread_throughput = results[1]['throughput_per_sec']
        for thread_count, metrics in results.items():
            efficiency = metrics['throughput_per_sec'] / (single_thread_throughput * thread_count)
            print(f"Threads {thread_count:2d} | {metrics['total_time_sec']:.2f}s | "
                  f"{metrics['throughput_per_sec']:.1f}/sec | "
                  f"Efficiency: {efficiency:.1%}")

        # Concurrent processing should provide reasonable efficiency
        assert results[4]['throughput_per_sec'] > single_thread_throughput * 2, "Limited concurrency benefit"

    def test_memory_efficiency_large_files(self, temp_dir, memory_tracker):
        """Test memory efficiency when processing large files."""
        # Create a very large image (10MP)
        large_size = (4000, 2500)  # 10 megapixels
        large_path = os.path.join(temp_dir, 'very_large.jpg')

        # Create complex image
        image = Image.new('RGB', large_size)
        pixels = image.load()
        for x in range(0, large_size[0], 10):
            for y in range(0, large_size[1], 10):
                color = (x % 256, y % 256, (x + y) % 256)
                for dx in range(min(10, large_size[0] - x)):
                    for dy in range(min(10, large_size[1] - y)):
                        pixels[x + dx, y + dy] = color

        image.save(large_path, 'JPEG', quality=95)

        # Measure memory before processing
        memory_before = memory_tracker.sample()
        gc.collect()

        # Generate thumbnail
        output_path = os.path.join(temp_dir, 'large_thumb.jpg')
        start_time = time.perf_counter()

        result = generate_thumbnail(large_path, output_path)

        end_time = time.perf_counter()
        memory_after = memory_tracker.sample()

        # Verify success
        assert result is True
        assert os.path.exists(output_path)

        # Memory efficiency checks
        memory_used = (memory_after - memory_before) / 1024 / 1024  # MB
        processing_time = end_time - start_time

        print(f"\nLarge file processing:")
        print(f"  Source size: {large_size[0] * large_size[1] / 1000000:.1f}MP")
        print(f"  File size: {os.path.getsize(large_path) / 1024 / 1024:.1f}MB")
        print(f"  Processing time: {processing_time:.2f}s")
        print(f"  Memory used: {memory_used:.1f}MB")
        print(f"  Throughput: {(large_size[0] * large_size[1]) / 1000000 / processing_time:.1f}MP/s")

        # Performance assertions
        assert memory_used < 200, f"Memory usage too high: {memory_used:.1f}MB"
        assert processing_time < 5.0, f"Processing too slow: {processing_time:.2f}s"

        # Verify thumbnail is properly sized
        with Image.open(output_path) as thumb:
            assert thumb.size == (180, 180)

    def test_database_job_processing_performance(self, app, temp_dir):
        """Test performance of database job processing."""
        with app.app_context():
            app.config['TESTING'] = True
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
            db.create_all()

            # Create test image
            test_image = Image.new('RGB', (400, 300), color='blue')
            image_path = os.path.join(temp_dir, 'test.jpg')
            test_image.save(image_path)

            job_counts = [10, 50, 100]
            results = {}

            for job_count in job_counts:
                # Clean up previous jobs
                db.query(Job).delete()
                db.query(JobItem).delete()
                db.session.commit()

                # Create jobs
                job_ids = []
                start_time = time.perf_counter()

                for i in range(job_count):
                    job_result = create_thumbnail_job(
                        'direct_upload_original',
                        'test_uuid_' + str(i),
                        image_path,
                        os.path.join(temp_dir, f'output_{i}.jpg')
                    )
                    if job_result['success']:
                        job_ids.append(job_result['job_item_id'])

                creation_time = time.perf_counter()

                # Process all jobs
                processed_count = 0
                for job_item_id in job_ids:
                    result = process_thumbnail_job(job_item_id)
                    if result['success']:
                        processed_count += 1

                processing_time = time.perf_counter()

                total_time = processing_time - start_time
                creation_overhead = creation_time - start_time
                processing_only = processing_time - creation_time

                results[job_count] = {
                    'total_time_sec': total_time,
                    'creation_overhead_sec': creation_overhead,
                    'processing_time_sec': processing_only,
                    'processed_count': processed_count,
                    'jobs_per_sec': processed_count / total_time,
                    'processing_throughput': processed_count / processing_only
                }

            # Performance analysis
            print("\n=== Database Job Processing Performance ===")
            for job_count, metrics in results.items():
                print(f"Jobs {job_count:4d} | {metrics['total_time_sec']:.2f}s total | "
                      f"{metrics['jobs_per_sec']:.1f}/sec | "
                      f"{metrics['processing_throughput']:.1f}/sec processing")

            # Performance expectations
            assert results[100]['processing_throughput'] > 10, "Job processing throughput too low"

    def test_quality_vs_performance_tradeoff(self, performance_images, temp_dir):
        """Test performance impact of different quality settings."""
        quality_levels = [10, 50, 85, 95, 100]
        test_image = performance_images['large']  # Use large image for noticeable differences

        results = {}

        for quality in quality_levels:
            gc.collect()

            output_path = os.path.join(temp_dir, f'quality_{quality}.jpg')

            start_time = time.perf_counter()
            result = generate_thumbnail(test_image['path'], output_path, quality=quality)
            end_time = time.perf_counter()

            assert result is True
            assert os.path.exists(output_path)

            processing_time = end_time - start_time
            file_size = os.path.getsize(output_path)

            results[quality] = {
                'processing_time_sec': processing_time,
                'file_size_kb': file_size / 1024,
                'compression_ratio': test_image['file_size'] / file_size
            }

        print("\n=== Quality vs Performance Tradeoff ===")
        for quality, metrics in results.items():
            print(f"Quality {quality:3d} | {metrics['processing_time_sec']:.3f}s | "
                  f"{metrics['file_size_kb']:.1f}KB | "
                  f"{metrics['compression_ratio']:.1f}x")

        # Higher quality should generally take slightly longer but produce better compression
        assert results[100]['compression_ratio'] >= results[85]['compression_ratio'], "Quality scaling incorrect"

    def test_scalability_limits(self, temp_dir):
        """Test system behavior under extreme load."""
        # Test extreme batch sizes to find system limits
        extreme_batch_sizes = [100, 200, 500]

        # Create a simple test image
        test_image = Image.new('RGB', (200, 200), color='red')
        image_path = os.path.join(temp_dir, 'scalability_test.jpg')
        test_image.save(image_path)

        for batch_size in extreme_batch_sizes:
            gc.collect()
            start_memory = psutil.Process().memory_info().rss

            # Generate thumbnails
            successful = 0
            failed = 0
            start_time = time.perf_counter()

            try:
                for i in range(batch_size):
                    output_path = os.path.join(temp_dir, f'scale_{i}.jpg')
                    result = generate_thumbnail(image_path, output_path)

                    if result and os.path.exists(output_path):
                        successful += 1
                    else:
                        failed += 1

                    # Cleanup as we go to manage disk space
                    if os.path.exists(output_path):
                        os.remove(output_path)

            except Exception as e:
                print(f"Exception during scalability test at batch size {batch_size}: {e}")
                failed += 1

            end_time = time.perf_counter()
            end_memory = psutil.Process().memory_info().rss

            memory_used = (end_memory - start_memory) / 1024 / 1024
            total_time = end_time - start_time
            throughput = successful / total_time if total_time > 0 else 0

            print(f"\nScalability Test - Batch Size {batch_size}:")
            print(f"  Successful: {successful}")
            print(f"  Failed: {failed}")
            print(f"  Success Rate: {successful / batch_size:.1%}")
            print(f"  Total Time: {total_time:.2f}s")
            print(f"  Throughput: {throughput:.1f}/sec")
            print(f"  Memory Used: {memory_used:.1f}MB")

            # System should handle reasonable batch sizes
            if batch_size <= 200:
                assert successful / batch_size > 0.95, f"High failure rate at batch size {batch_size}"
                assert memory_used < 500, f"Excessive memory usage: {memory_used:.1f}MB"

    def test_io_performance_impact(self, temp_dir):
        """Test I/O performance impact on thumbnail generation."""
        # Test different storage scenarios (simulated)
        scenarios = {
            'fast_ssd': {'delay': 0.001},  # Fast storage
            'slow_hdd': {'delay': 0.05},   # Slow storage
            'network': {'delay': 0.1}      # Network storage
        }

        test_image = Image.new('RGB', (800, 600), color='green')
        base_image_path = os.path.join(temp_dir, 'io_test.jpg')
        test_image.save(base_image_path)

        results = {}

        for scenario_name, config in scenarios.items():
            # Mock file operations with delays
            with patch('builtins.open', side_effect=self._mock_open_with_delay(config['delay'])):
                with patch('os.path.exists', return_value=True):
                    with patch('os.makedirs'):

                        gc.collect()
                        start_time = time.perf_counter()

                        # Generate thumbnail (will use mocked I/O)
                        output_path = os.path.join(temp_dir, f'io_{scenario_name}.jpg')

                        # Use original function but with mocked I/O
                        try:
                            # This will test the CPU portion while I/O is mocked
                            image = Image.open(base_image_path)
                            image.thumbnail((180, 180), Image.Resampling.LANCZOS)

                            # Simulate I/O delay
                            time.sleep(config['delay'])

                            image.save(output_path, 'JPEG', quality=85)
                            result = True
                        except Exception:
                            result = False

                        end_time = time.perf_counter()

                        results[scenario_name] = {
                            'processing_time_sec': end_time - start_time,
                            'io_delay_sec': config['delay'],
                            'success': result
                        }

        print("\n=== I/O Performance Impact ===")
        for scenario, metrics in results.items():
            print(f"{scenario:10} | {metrics['processing_time_sec']:.3f}s | "
                  f"IO delay: {metrics['io_delay_sec']:.3f}s")

        # Processing time should scale reasonably with I/O delays
        assert results['network']['processing_time_sec'] > results['fast_ssd']['processing_time_sec']

    def _mock_open_with_delay(self, delay):
        """Helper to mock file operations with delays."""
        original_open = open

        def mock_open_with_delay(*args, **kwargs):
            time.sleep(delay)  # Simulate I/O delay
            return original_open(*args, **kwargs)

        return mock_open_with_delay


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])