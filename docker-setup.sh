#!/bin/bash
set -e

echo "╔═══════════════════════════════════════════════════╗"
echo "║   Automated Budgeting Tool - Docker Setup        ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed!"
    echo ""
    echo "Install Docker with:"
    echo "  Ubuntu/Debian: sudo apt install docker.io docker-compose"
    echo "  Mac: Download from https://docker.com/products/docker-desktop"
    echo ""
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed!"
    echo ""
    echo "Install with:"
    echo "  Ubuntu/Debian: sudo apt install docker-compose"
    echo "  Mac: Included with Docker Desktop"
    echo ""
    exit 1
fi

echo "✅ Docker found: $(docker --version 2>&1 | head -n1 || echo 'version check failed')"
echo "✅ docker-compose found: $(docker-compose --version 2>&1 | head -n1 || echo 'version check failed')"
echo ""

# Check if Ollama is running on host
if command -v curl &> /dev/null && curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama detected on host (port 11434)"
    echo "   Docker will use your existing Ollama installation"
    echo ""
else
    echo "⚠️  Ollama not detected on port 11434"
    echo "   Make sure Ollama is installed and running:"
    echo "   - Install: curl -fsSL https://ollama.com/install.sh | sh"
    echo "   - Start: ollama serve (or it may already be running as a service)"
    echo ""
    echo "   Continuing anyway - you can start Ollama later..."
    echo ""
fi

# Check if user is in docker group
USE_SUDO=""
if ! groups | grep -q docker; then
    echo "⚠️  You're not in the docker group."
    echo ""
    echo "Choose an option:"
    echo "  1. Use sudo for this session (quick, works now)"
    echo "  2. Add to docker group (permanent, requires logout)"
    echo ""
    read -p "Enter choice [1/2]: " choice
    
    if [ "$choice" = "2" ]; then
        echo ""
        echo "Adding you to docker group..."
        sudo usermod -aG docker $USER
        echo ""
        echo "✅ Added to docker group!"
        echo ""
        echo "⚠️  You MUST log out and back in for this to take effect."
        echo "   After logging back in, run this script again: ./docker-setup.sh"
        echo ""
        exit 0
    else
        echo ""
        echo "Using sudo for Docker commands..."
        USE_SUDO="sudo"
    fi
    echo ""
fi

# Build images
echo "🔨 Building Docker images..."
echo "   This may take 5-10 minutes on first run..."
echo ""
$USE_SUDO docker-compose build

echo ""
echo "✅ Build complete!"
echo ""

# Start services
echo "🚀 Starting services..."
$USE_SUDO docker-compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

# Check if services are running
if $USE_SUDO docker-compose ps | grep -q "Up"; then
    echo ""
    echo "✅ Services started successfully!"
    echo ""
    echo "╔═══════════════════════════════════════════════════╗"
    echo "║             Services Ready!                       ║"
    echo "╠═══════════════════════════════════════════════════╣"
    echo "║  Dashboard:    http://localhost:8000              ║"
    echo "║  Ollama API:   http://localhost:11434 (host)      ║"
    echo "╚═══════════════════════════════════════════════════╝"
    echo ""
    if [ -n "$USE_SUDO" ]; then
        echo "⚠️  NOTE: Using sudo for Docker commands."
        echo "   Use 'sudo make ...' for all make commands."
        echo ""
        echo "📦 Next: Ensure you have required AI models on HOST:"
        echo "   ollama pull gemma3:27b"
        echo "   ollama pull qwen3:32b"
        echo ""
        echo "   Or use: make models (no sudo needed)"
        echo ""
        echo "📄 Process statements with:"
        echo "   sudo make process MONTH=2025-03"
        echo ""
        echo "🛑 Stop services with:"
        echo "   sudo make down"
        echo ""
        echo "💡 TIP: To avoid sudo, add yourself to docker group:"
        echo "   sudo uEnsure you have required AI models on HOST:"
        echo "   ollama pull gemma3:27b"
        echo "   ollama pull qwen3:32b"
        echo ""
        echo "   Or use: make models"
        echo ""
        echo "📄 P: Pull AI models with:"
        echo "   make models"
        echo ""
        echo "📄 Or process statements with:"
        echo "   make process MONTH=2025-03"
        echo ""
        echo "📊 View logs with:"
        echo "   make logs"
        echo ""
        echo "🛑 Stop services with:"
        echo "   make down"
    fi
    echo ""
else
    echo "❌ Services failed to start. Check logs with:"
    if [ -n "$USE_SUDO" ]; then
        echo "   sudo docker-compose logs"
    else
        echo "   docker-compose logs"
    fi
    echo ""
    exit 1
fi
