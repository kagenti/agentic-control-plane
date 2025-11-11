FROM python:3.12-slim

WORKDIR /app

# Copy all files for package installation
COPY . /app/

# Install the package with dependencies
RUN pip install --no-cache-dir .

# Set proper permissions for OpenShift compatibility
RUN chmod -R g+rwX /app && \
    chgrp -R 0 /app

CMD ["python", "-c", "from a2a_agent import run; run()"]
