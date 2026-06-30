#!/bin/bash
set -e

echo "🚀 Starting Automated Budgeting Tool"

# Wait for Ollama to be ready (on host machine) - with timeout
echo "⏳ Checking for Ollama service..."
OLLAMA_URL="${OLLAMA_HOST:-http://host.docker.internal:11434}"
MAX_ATTEMPTS=10
ATTEMPT=0

# Try common host aliases/gateways used by Docker across platforms.
OLLAMA_CANDIDATES=(
    "${OLLAMA_URL}"
    "http://host.docker.internal:11434"
    "http://gateway.docker.internal:11434"
    "http://172.17.0.1:11434"
    "http://localhost:11434"
)

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    for CANDIDATE_URL in "${OLLAMA_CANDIDATES[@]}"; do
        if curl -s -f "${CANDIDATE_URL}/api/tags" > /dev/null 2>&1; then
            OLLAMA_URL="${CANDIDATE_URL}"
            # Ensure child Python processes use the same reachable URL.
            export OLLAMA_HOST="${OLLAMA_URL}"
            echo "✅ Ollama is ready at ${OLLAMA_URL}"
            break 2
        fi
    done
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
        echo "   Ollama not ready yet (attempt $ATTEMPT/$MAX_ATTEMPTS), waiting..."
        sleep 2
    fi
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "⚠️  Warning: Could not connect to Ollama from container."
    echo "   Tried: ${OLLAMA_CANDIDATES[*]}"
    echo "   Make sure Ollama is running on host: ollama serve"
    echo "   On Linux, if Ollama is bound to 127.0.0.1 only, run: OLLAMA_HOST=0.0.0.0:11434 ollama serve"
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
        if echo "$TAGS" | grep -F -q "\"${MODEL}\"" || echo "$TAGS" | grep -F -q "\"${MODEL}:"; then
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
