FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install dependencies
# --pre flag is required for pre-release packages like opentelemetry-instrumentation-openai-v2
COPY requirements.txt .
RUN pip install --no-cache-dir --pre -r requirements.txt

# Copy application code
COPY orchestrator_agent/ ./orchestrator_agent/
COPY a2a_agent.py .

# OpenShift compatibility: set group permissions for arbitrary UID
RUN chmod -R g+rwX /app && \
    chgrp -R 0 /app

# Run as non-root user
USER 1000

# Expose port
EXPOSE 8000

# Run the A2A agent
CMD ["python", "a2a_agent.py"]
