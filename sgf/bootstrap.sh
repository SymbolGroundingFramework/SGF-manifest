#!/usr/bin/env bash
# ==============================================================================
# Lexicon Bootstrapping Pipeline Script for SGF / Synapedia
# ==============================================================================
# This script orchestrates raw data ingestion and Synapedia DB generation:
# 1. WordNet raw XML -> wordnet.db
# 2. wordnet.db -> synapedia.db (initialization)
# 3. Wiktionary raw JSONL -> wiktionary_raw.db
# 4. wiktionary_raw.db -> synapedia.db (update)
# 5. Wikipedia abstracts JSON -> wikipedia.db
# 6. wikipedia.db -> synapedia.db (update)
# ==============================================================================

set -e

# Resolve repository root and sgf paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SGF_DIR="$SCRIPT_DIR"
cd "$SGF_DIR"

# Select Python environment
if [ -x "$SGF_DIR/.venv/bin/python" ]; then
    PYTHON="$SGF_DIR/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

# Define DB and directory locations
WORDNET_DB="$SGF_DIR/wordnet.db"
if [ -f "$SGF_DIR/wiktionary_raw.db" ]; then
    WIKTIONARY_DB="$SGF_DIR/wiktionary_raw.db"
elif [ -f "$SGF_DIR/wiktionary.db" ]; then
    WIKTIONARY_DB="$SGF_DIR/wiktionary.db"
else
    WIKTIONARY_DB="$SGF_DIR/wiktionary_raw.db"
fi
WIKIPEDIA_DB="$SGF_DIR/wikipedia.db"
SYNAPEDIA_DB="$SGF_DIR/synapedia.db"
SOURCEDATA_DIR="$SGF_DIR/sourcedata"

# Helper function to get database status and size
get_file_info() {
    local file="$1"
    if [ -f "$file" ]; then
        local size
        size=$(du -h "$file" 2>/dev/null | cut -f1)
        echo "Present ($size) - $file"
    else
        echo "Not present (0 bytes) - $file"
    fi
}

# Helper function to find raw data file in sourcedata/
find_raw_file() {
    local dir="$1"
    shift
    local patterns=("$@")
    if [ ! -d "$dir" ]; then
        return 1
    fi
    for pattern in "${patterns[@]}"; do
        local found
        found=$(find "$dir" -maxdepth 2 \( -name "$pattern" \) 2>/dev/null | head -n 1)
        if [ -n "$found" ] && [ -f "$found" ]; then
            echo "$found"
            return 0
        fi
    done
    return 1
}

# Helper function to prompt yes/no
prompt_yn() {
    local prompt_text="$1"
    local default="${2:-n}"
    local response

    if [[ "$default" =~ ^[Yy]$ ]]; then
        read -rp "$prompt_text [Y/n]: " response
        response="${response:-y}"
    else
        read -rp "$prompt_text [y/N]: " response
        response="${response:-n}"
    fi

    case "$response" in
        [Yy]*) echo "true" ;;
        *)     echo "false" ;;
    esac
}

echo "======================================================================"
echo "                   SGF Lexicon Bootstrap Setup"
echo "======================================================================"
echo "Responses for all 6 steps will be collected before execution starts."
echo "Raw files should be placed in: $SOURCEDATA_DIR"
echo "======================================================================"
echo

# ------------------------------------------------------------------------------
# STEP 1: WordNet Raw Ingestion Prompt
# ------------------------------------------------------------------------------
echo "[Step 1] WordNet Database Ingestion"
echo "  Current DB status: $(get_file_info "$WORDNET_DB")"
DO_IMPORT_WORDNET_RAW=$(prompt_yn "  Import WordNet raw data from sourcedata/?")
echo

# ------------------------------------------------------------------------------
# STEP 2: Synapedia from WordNet Prompt
# ------------------------------------------------------------------------------
echo "[Step 2] Synapedia DB Generation (from WordNet)"
DO_GENERATE_SYNAPEDIA_WORDNET=$(prompt_yn "  Generate/initialize Synapedia DB from wordnet.db?")
echo

# ------------------------------------------------------------------------------
# STEP 3: Wiktionary Raw Ingestion Prompt
# ------------------------------------------------------------------------------
echo "[Step 3] Wiktionary Database Ingestion"
echo "  Current DB status: $(get_file_info "$WIKTIONARY_DB")"
DO_IMPORT_WIKTIONARY_RAW=$(prompt_yn "  Import Wiktionary raw data from sourcedata/?")
echo

# ------------------------------------------------------------------------------
# STEP 4: Synapedia from Wiktionary Prompt
# ------------------------------------------------------------------------------
echo "[Step 4] Synapedia DB Update (from Wiktionary)"
DO_UPDATE_SYNAPEDIA_WIKTIONARY=$(prompt_yn "  Update Synapedia DB from wiktionary DB?")
echo

# ------------------------------------------------------------------------------
# STEP 5: Wikipedia Raw Ingestion Prompt
# ------------------------------------------------------------------------------
echo "[Step 5] Wikipedia Database Ingestion"
echo "  Current DB status: $(get_file_info "$WIKIPEDIA_DB")"
DO_IMPORT_WIKIPEDIA_RAW=$(prompt_yn "  Import Wikipedia raw data from sourcedata/?")
echo

# ------------------------------------------------------------------------------
# STEP 6: Synapedia from Wikipedia Prompt
# ------------------------------------------------------------------------------
echo "[Step 6] Synapedia DB Update (from Wikipedia)"
DO_UPDATE_SYNAPEDIA_WIKIPEDIA=$(prompt_yn "  Update Synapedia DB from wikipedia.db?")
echo

# ------------------------------------------------------------------------------
# STEP 7: Postprocessing Prompt (Microgloss & Fragment Index)
# ------------------------------------------------------------------------------
echo "[Step 7] Postprocessing (Generate Microglosses & Canonical IDs)"
DO_RUN_MICROGLOSS=$(prompt_yn "  Run create_microgloss.py & build_fragment_index.py on synapedia.db?")
echo

# ------------------------------------------------------------------------------
# SUMMARY & CONFIRMATION
# ------------------------------------------------------------------------------
echo "======================================================================"
echo "                      CONFIGURATION SUMMARY"
echo "======================================================================"
echo "  1. Import WordNet raw data:          $([ "$DO_IMPORT_WORDNET_RAW" = "true" ] && echo "YES" || echo "NO")"
echo "  2. Generate Synapedia from WordNet: $([ "$DO_GENERATE_SYNAPEDIA_WORDNET" = "true" ] && echo "YES" || echo "NO")"
echo "  3. Import Wiktionary raw data:       $([ "$DO_IMPORT_WIKTIONARY_RAW" = "true" ] && echo "YES" || echo "NO")"
echo "  4. Update Synapedia from Wiktionary: $([ "$DO_UPDATE_SYNAPEDIA_WIKTIONARY" = "true" ] && echo "YES" || echo "NO")"
echo "  5. Import Wikipedia raw data:       $([ "$DO_IMPORT_WIKIPEDIA_RAW" = "true" ] && echo "YES" || echo "NO")"
echo "  6. Update Synapedia from Wikipedia: $([ "$DO_UPDATE_SYNAPEDIA_WIKIPEDIA" = "true" ] && echo "YES" || echo "NO")"
echo "  7. Postprocessing (Microgloss):     $([ "$DO_RUN_MICROGLOSS" = "true" ] && echo "YES" || echo "NO")"
echo "======================================================================"
echo

CONFIRM_EXEC=$(prompt_yn "Proceed with execution of the selected steps?")
if [ "$CONFIRM_EXEC" != "true" ]; then
    echo "Bootstrap execution cancelled."
    exit 0
fi

echo
echo "======================================================================"
echo "                     STARTING BOOTSTRAP EXECUTION"
echo "======================================================================"
echo

# Ensure sourcedata directory exists
mkdir -p "$SOURCEDATA_DIR"

# ------------------------------------------------------------------------------
# EXECUTION STEP 1: Import WordNet raw data
# ------------------------------------------------------------------------------
if [ "$DO_IMPORT_WORDNET_RAW" = "true" ]; then
    echo ">>> Running Step 1: Importing WordNet raw data..."
    WN_RAW_FILE=$(find_raw_file "$SOURCEDATA_DIR" "english-wordnet-*.xml*" "*wordnet*.xml*" "*.xml" "*.xml.gz" || true)
    if [ -n "$WN_RAW_FILE" ]; then
        echo "Found WordNet raw file: $WN_RAW_FILE"
        "$PYTHON" "$SGF_DIR/synapedia/wordnet/load_wordnet.py" --xml "$WN_RAW_FILE" --db "$WORDNET_DB"
        echo "Step 1 completed. Output DB: $(get_file_info "$WORDNET_DB")"
    else
        echo "ERROR: No WordNet raw XML file found in $SOURCEDATA_DIR."
        echo "Please place an OEWN XML file (e.g. english-wordnet-2025.xml.gz) in $SOURCEDATA_DIR/"
    fi
    echo
fi

# ------------------------------------------------------------------------------
# EXECUTION STEP 2: Generate Synapedia DB from wordnet.db
# ------------------------------------------------------------------------------
if [ "$DO_GENERATE_SYNAPEDIA_WORDNET" = "true" ]; then
    echo ">>> Running Step 2: Generating Synapedia DB from wordnet.db..."
    if [ -f "$WORDNET_DB" ]; then
        "$PYTHON" "$SGF_DIR/synapedia/bootstrapping/load_synapedia_from_wordnet_db.py" \
            --wordnet-db "$WORDNET_DB" \
            --synapedia-db "$SYNAPEDIA_DB" \
            --reset
        echo "Step 2 completed. Synapedia DB: $(get_file_info "$SYNAPEDIA_DB")"
    else
        echo "ERROR: WordNet DB ($WORDNET_DB) not found. Run Step 1 first or provide wordnet.db."
    fi
    echo
fi

# ------------------------------------------------------------------------------
# EXECUTION STEP 3: Import Wiktionary raw data
# ------------------------------------------------------------------------------
if [ "$DO_IMPORT_WIKTIONARY_RAW" = "true" ]; then
    echo ">>> Running Step 3: Importing Wiktionary raw data..."
    WIKT_RAW_FILE=$(find_raw_file "$SOURCEDATA_DIR" "*wiktextract*.jsonl*" "*wiktionary*.jsonl*" "*extract*.jsonl*" "*.jsonl" "*.jsonl.gz" || true)
    if [ -n "$WIKT_RAW_FILE" ]; then
        echo "Found Wiktionary raw file: $WIKT_RAW_FILE"
        "$PYTHON" "$SGF_DIR/synapedia/wiktionary/load_wiktionary_to_db.py" --source "$WIKT_RAW_FILE" --target "$WIKTIONARY_DB"
        echo "Step 3 completed. Output DB: $(get_file_info "$WIKTIONARY_DB")"
    else
        echo "ERROR: No Wiktionary raw JSONL file found in $SOURCEDATA_DIR."
        echo "Please place a Kaikki JSONL dump (e.g. raw-wiktextract-data.jsonl) in $SOURCEDATA_DIR/"
    fi
    echo
fi

# ------------------------------------------------------------------------------
# EXECUTION STEP 4: Update Synapedia DB from wiktionary.db
# ------------------------------------------------------------------------------
if [ "$DO_UPDATE_SYNAPEDIA_WIKTIONARY" = "true" ]; then
    echo ">>> Running Step 4: Updating Synapedia DB from wiktionary DB..."
    if [ -f "$WIKTIONARY_DB" ] && [ -f "$SYNAPEDIA_DB" ]; then
        "$PYTHON" "$SGF_DIR/synapedia/bootstrapping/load_synapedia_from_wiktionary.py" \
            --wiktionary-db "$WIKTIONARY_DB" \
            --synapedia-db "$SYNAPEDIA_DB" #--workers 1
        echo "Step 4 completed. Synapedia DB: $(get_file_info "$SYNAPEDIA_DB")"
    else
        echo "ERROR: Either Wiktionary DB ($WIKTIONARY_DB) or Synapedia DB ($SYNAPEDIA_DB) was not found."
    fi
    echo
fi

# ------------------------------------------------------------------------------
# EXECUTION STEP 5: Import Wikipedia raw data
# ------------------------------------------------------------------------------
if [ "$DO_IMPORT_WIKIPEDIA_RAW" = "true" ]; then
    echo ">>> Running Step 5: Importing Wikipedia raw data..."
    WIKI_JSON_FILE=$(find_raw_file "$SOURCEDATA_DIR" "abstracts.json" "*wikipedia*.json" "*.json" || true)
    if [ -n "$WIKI_JSON_FILE" ]; then
        echo "Found Wikipedia abstracts JSON: $WIKI_JSON_FILE"
        "$PYTHON" "$SGF_DIR/synapedia/wikipedia/load_wikipedia.py" --source "$WIKI_JSON_FILE" --target "$WIKIPEDIA_DB"
        echo "Step 5 completed. Output DB: $(get_file_info "$WIKIPEDIA_DB")"
    else
        WIKI_TTL_FILE=$(find_raw_file "$SOURCEDATA_DIR" "*.ttl" "*.ttl.bz2" || true)
        if [ -n "$WIKI_TTL_FILE" ]; then
            echo "Found Wikipedia TTL dump: $WIKI_TTL_FILE. Extracting abstracts..."
            "$PYTHON" "$SGF_DIR/synapedia/wikipedia/extract_abstracts.py"
            if [ -f "abstracts.json" ]; then
                "$PYTHON" "$SGF_DIR/synapedia/wikipedia/load_wikipedia.py" --source "abstracts.json" --target "$WIKIPEDIA_DB"
                echo "Step 5 completed. Output DB: $(get_file_info "$WIKIPEDIA_DB")"
            fi
        else
            echo "ERROR: No Wikipedia abstracts file (abstracts.json or *.ttl) found in $SOURCEDATA_DIR."
            echo "Please place abstracts.json or short-abstracts.ttl in $SOURCEDATA_DIR/"
        fi
    fi
    echo
fi

# ------------------------------------------------------------------------------
# EXECUTION STEP 6: Update Synapedia DB from wikipedia.db
# ------------------------------------------------------------------------------
if [ "$DO_UPDATE_SYNAPEDIA_WIKIPEDIA" = "true" ]; then
    echo ">>> Running Step 6: Updating Synapedia DB from wikipedia.db..."
    if [ -f "$WIKIPEDIA_DB" ] && [ -f "$SYNAPEDIA_DB" ]; then
        "$PYTHON" "$SGF_DIR/synapedia/bootstrapping/load_synapedia_from_wikipedia.py" \
            --wikipedia-db "$WIKIPEDIA_DB" \
            --synapedia-db "$SYNAPEDIA_DB"
        echo "Step 6 completed. Synapedia DB: $(get_file_info "$SYNAPEDIA_DB")"
    else
        echo "ERROR: Either Wikipedia DB ($WIKIPEDIA_DB) or Synapedia DB ($SYNAPEDIA_DB) was not found."
    fi
    echo
fi

# ------------------------------------------------------------------------------
# EXECUTION STEP 7: Postprocessing (Microgloss & Fragment Index)
# ------------------------------------------------------------------------------
if [ "$DO_RUN_MICROGLOSS" = "true" ]; then
    echo ">>> Running Step 7: Generating microglosses and canonical IDs..."
    if [ -f "$SYNAPEDIA_DB" ]; then
        "$PYTHON" "$SGF_DIR/synapedia/bootstrapping/create_microgloss.py" --target "$SYNAPEDIA_DB" --force
        "$PYTHON" "$SGF_DIR/synapedia/bootstrapping/build_fragment_index.py" --db "$SYNAPEDIA_DB"
        echo "Step 7 completed. Synapedia DB postprocessed: $(get_file_info "$SYNAPEDIA_DB")"
    else
        echo "ERROR: Synapedia DB ($SYNAPEDIA_DB) not found."
    fi
    echo
fi

echo "======================================================================"
echo "                     BOOTSTRAP WORKFLOW FINISHED"
echo "======================================================================"
