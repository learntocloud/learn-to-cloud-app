#!/bin/bash
set -e

echo "Running database migrations..."
python -m scripts.create_tables
echo "Database migrations completed"

echo "Starting application..."
exec "$@"
