FROM python:3.12-slim 

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .
COPY lib/ ./lib/

# Run as non-root user
RUN useradd -m -u 1000 mcp && chown -R mcp:mcp /app
USER mcp

# Expose port (MCP servers typically use SSE, common port 8000)
EXPOSE 8000

# Run the MCP server
CMD ["python", "server.py"]
