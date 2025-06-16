# 1. Base image with Python & system tools
FROM python:3.11-slim

# 2. Install node, npm, git, curl
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
      curl \
      git \
      gnupg2 && \
    # Node.js 18.x
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    # Install Astral uv, and make it available globally
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    cp /root/.local/bin/uv /usr/local/bin/uv && \
    cp /root/.local/bin/uvx /usr/local/bin/uvx && \
    # cleanup
    apt-get purge -y --auto-remove curl gnupg2 && \
    rm -rf /var/lib/apt/lists/*

# 3. Create & switch to non-root user
ARG UNAME=developer
ARG UID=1000
RUN useradd --create-home --shell /bin/bash --uid $UID $UNAME

USER $UNAME
WORKDIR /home/$UNAME/chatty

# 4. Copy the entire project
COPY --chown=$UNAME:$UNAME . .

# 5. Expose app port
EXPOSE 8000

# 6. Run chatty
ENTRYPOINT ["uv", "run", "chatty.py"]
CMD ["--ollama", "http://host.docker.internal:11434", \
     "--host", "0.0.0.0", "--port", "8000", "--reload"]