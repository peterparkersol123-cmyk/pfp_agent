#!/bin/bash

# Pump.fun X/Twitter AI Agent - Run Script

echo "========================================="
echo "Pump.fun X/Twitter AI Agent"
echo "========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if [ ! -f "venv/installed" ]; then
    echo "Installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
    touch venv/installed
    echo "✓ Dependencies installed"
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠ Warning: .env file not found!"
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo ""
    echo "Please edit .env file with your API keys before running the agent."
    echo "Required:"
    echo "  - ANTHROPIC_API_KEY"
    echo "  - Twitter API credentials"
    echo ""
    exit 1
fi

# Run the agent
echo "Starting agent..."
echo ""
python -m src.main

# Deactivate on exit
deactivate
