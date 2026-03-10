#!/bin/bash
set -e

echo "🚀 Starting Automated Budgeting Tool"

# Wait for Ollama to be ready (on host machine) - with timeout
echo "⏳ Checking for Ollama service..."
OLLAMA_URL="${OLLAMA_HOST:-http://localhost:11434}"
MAX_ATTEMPTS=10
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -s -f "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
        echo "✅ Ollama is ready at ${OLLAMA_URL}"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
        echo "   Ollama not ready yet (attempt $ATTEMPT/$MAX_ATTEMPTS), waiting..."
        sleep 2
    fi
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "⚠️  Warning: Could not connect to Ollama at ${OLLAMA_URL}"
    echo "   Make sure Ollama is running on host: ollama serve"
    echo "   The application will start anyway, but AI features may not work."
    echo ""
else
    # Read model names from config/llm_models.json so checks always reflect actual config
    CONFIG_FILE="/app/config/llm_models.json"
    PRIMARY_MODEL=""
    SECONDARY_MODEL=""
    FINANCIAL_MODEL=""

    if [ -f "$CONFIG_FILE" ] && command -v python3 &> /dev/null; then
        PRIMARY_MODEL=$(python3 -c "import json,sys; d=json.load(open('$CONFIG_FILE')); print(d.get('primary_model',''))" 2>/dev/null || true)
        SECONDARY_MODEL=$(python3 -c "import json,sys; d=json.load(open('$CONFIG_FILE')); print(d.get('secondary_model',''))" 2>/dev/null || true)
        FINANCIAL_MODEL=$(python3 -c "import json,sys; d=json.load(open('$CONFIG_FILE')); print(d.get('financial_analysis_model',''))" 2>/dev/null || true)
    fi

    # Check each configured model
    echo "🔍 Checking for configured models..."
    TAGS=$(curl -s "${OLLAMA_URL}/api/tags")

    for MODEL_ENTRY in "${PRIMARY_MODEL}||primary" "${SECONDARY_MODEL}||secondary (ensemble)" "${FINANCIAL_MODEL}||financial analysis"; do
        MODEL="${MODEL_ENTRY%%||*}"
        ROLE="${MODEL_ENTRY##*||}"
        [ -z "$MODEL" ] && continue
        if echo "$TAGS" | grep -q "\"${MODEL}\"" || echo "$TAGS" | grep -q "\"${MODEL}:"; then
            echo "✅ Model found: ${MODEL} (${ROLE})"
        else
            echo "📥 Model not found: ${MODEL} (${ROLE}) — pulling now..."
            echo "   This may take several minutes for large models."
            LAST_PULL_LINE=$(curl -s -X POST "${OLLAMA_URL}/api/pull" \
                -H "Content-Type: application/json" \
                -d "{\"name\": \"${MODEL}\"}" | tail -1)
            if echo "$LAST_PULL_LINE" | grep -q '"success"'; then
                echo "✅ Successfully pulled: ${MODEL}"
            else
                echo "⚠️  Pull may have failed for ${MODEL}"
                echo "   If AI features are missing, pull manually on host: ollama pull ${MODEL}"
            fi
        fi
    done

    if [ -z "$PRIMARY_MODEL" ]; then
        echo "⚠️  Could not read model config from ${CONFIG_FILE}"
        echo "   Make sure config/llm_models.json exists with a 'primary_model' key."
    fi
fi

echo "✨ Setup complete!"
echo ""

# Execute the main command
exec "$@"
