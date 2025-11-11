FROM python:3.12-slim 

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .
COPY lib/ ./lib/

# OpenShift compatibility: set group permissions for arbitrary UID
RUN chmod -R g+rwX /app && \
    chgrp -R 0 /app

# Run as non-root user (OpenShift will use random UID with gid 0)
USER 1000

# Expose port (MCP servers typically use SSE, common port 8000)
EXPOSE 8000

# Run the MCP server
CMD ["python", "server.py"]
