#!/bin/bash
# Test runner script with PostgreSQL test database
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Docker compose command
DC="docker compose --env-file deploy.config.env --env-file deploy.secrets.env"

echo -e "${YELLOW}🧪 Starting test database...${NC}"

# Start test database
$DC up test-db -d

# Wait for database to be ready
echo -e "${YELLOW}⏳ Waiting for test database to be ready...${NC}"
timeout 30 bash -c 'until docker exec fundus-img-xtract-test-db pg_isready -U test_user -d fundus_test 2>/dev/null; do sleep 1; done' || {
    echo -e "${RED}❌ Test database failed to start${NC}"
    exit 1
}

echo -e "${GREEN}✅ Test database ready!${NC}"

# Run tests
echo -e "${YELLOW}🧪 Running tests...${NC}"
$DC exec web uv run pytest "$@"

TEST_EXIT_CODE=$?

# Cleanup is optional - test DB uses tmpfs so no disk cleanup needed
# Uncomment to stop test DB after tests:
# echo -e "${YELLOW}🧹 Stopping test database...${NC}"
# $DC stop test-db

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Tests passed!${NC}"
else
    echo -e "${RED}❌ Tests failed with exit code $TEST_EXIT_CODE${NC}"
fi

exit $TEST_EXIT_CODE
