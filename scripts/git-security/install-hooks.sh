#!/bin/bash
# Install security hooks to a git repository
# Usage: install-hooks.sh /path/to/repo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/pre-commit-template"

if [ -z "$1" ]; then
    echo "Usage: $0 /path/to/repo"
    exit 1
fi

REPO_PATH="$1"
HOOKS_DIR="$REPO_PATH/.git/hooks"

if [ ! -d "$REPO_PATH/.git" ]; then
    echo "❌ Not a git repository: $REPO_PATH"
    exit 1
fi

if [ ! -f "$TEMPLATE" ]; then
    echo "❌ Template not found: $TEMPLATE"
    exit 1
fi

# Install pre-commit hook
mkdir -p "$HOOKS_DIR"
cp "$TEMPLATE" "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-commit"

echo "✅ Installed pre-commit hook to: $REPO_PATH"

# Also create/update .gitignore with common secret patterns
GITIGNORE="$REPO_PATH/.gitignore"
PATTERNS_TO_ADD=(
    "# Security - never commit these"
    ".env"
    ".env.*"
    "*.pem"
    "*.key"
    ".htpasswd"
    ".htaccess"
    "credentials.json"
    "secrets.json"
    "service-account*.json"
    "**/id_rsa"
    "**/id_ed25519"
)

echo ""
echo "Checking .gitignore..."
for pattern in "${PATTERNS_TO_ADD[@]}"; do
    if ! grep -qF "$pattern" "$GITIGNORE" 2>/dev/null; then
        echo "$pattern" >> "$GITIGNORE"
        echo "  Added: $pattern"
    fi
done

echo "✅ .gitignore updated"
