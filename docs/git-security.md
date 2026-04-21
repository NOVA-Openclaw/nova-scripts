# Git Security Hooks

A simple pre‑commit hook that scans staged files for potential secrets and blocks commits if any are detected.

## Installation

Run the installer script on any Git repository you want to protect:

```bash
./scripts/git-security/install-hooks.sh /path/to/your/repo
```

This will:

1. Copy `scripts/git-security/pre-commit-template` to `.git/hooks/pre-commit`.
2. Make the hook executable.
3. Add common secret‑file patterns to the repository's `.gitignore` (if they aren't already there).

## What It Detects

### Secret Patterns

The hook uses `grep` with regular expressions to find:

| Pattern | Example | Notes |
|---------|---------|-------|
| Anthropic API key | `sk-ant-api…` | `sk-ant-api[0-9a-zA-Z_-]+` |
| Anthropic Admin key | `sk-ant-admin…` | `sk-ant-admin[0-9a-zA-Z_-]+` |
| OpenAI API key | `sk-…` | `sk-[a-zA-Z0-9]{20,}` |
| AWS Access Key | `AKIA…` | `AKIA[A-Z0-9]{16}` |
| AWS Secret Key | `"…40‑char…"` | `['"][0-9a-zA-Z/+]{40}['"]` |
| Private Key header | `-----BEGIN … PRIVATE KEY-----` | `-----BEGIN[A-Z ]*PRIVATE KEY-----` |
| GitHub Token | `ghp_…`, `gho_…` | `gh[pousr]_[A-Za-z0-9_]{36,}` |
| Generic secret | `secret: "value"` | `['"]?[sS]ecret['"]?\s*[:=]\s*['"][^'"]{8,}['"]` |
| Generic password | `password: "value"` | `['"]?[pP]assword['"]?\s*[:=]\s*['"][^'"]{8,}['"]` |
| Generic API key | `api_key: "value"` | `['"]?[aA]pi[_-]?[kK]ey['"]?\s*[:=]\s*['"][^'"]{16,}['"]` |

### Forbidden Files

The hook also blocks commits of files whose names match any of these patterns:

- `.htpasswd`
- `.htaccess`
- `.env`, `.env.local`, `.env.production`
- `id_rsa`, `id_ed25519`
- `*.pem`
- `credentials.json`
- `secrets.json`
- `service‑account*.json`

## How It Works

1. On `git commit`, the hook runs and gets the list of staged files (`git diff --cached --name-only`).
2. It scans each file for the secret patterns and checks filenames against the forbidden list.
3. If any matches are found, the hook prints the offending lines/filenames and exits with code 1, blocking the commit.
4. If no matches, the hook exits with code 0 and the commit proceeds.

### Example Output

```
🔍 Scanning for secrets...
⚠️  Potential OpenAI API key in config.yaml:
12:  api_key: "sk-abc123..."
❌ BLOCKED: .env matches forbidden pattern (\.env$)

❌ Commit blocked due to potential secrets.
   Review the files above and remove sensitive data.
   If this is a FALSE POSITIVE, you may use:
     git commit --no-verify
   But document why in your commit message!
```

## Bypassing the Hook (When Necessary)

If you need to commit something that triggers a false positive (e.g., a placeholder key in documentation), you can bypass the hook with:

```bash
git commit --no-verify
```

**Important:** Always document why you bypassed the hook in the commit message.

## Customization

### Adding Your Own Patterns

Edit the `pre-commit-template` file (or the installed `.git/hooks/pre-commit`) and extend the `PATTERNS` associative array:

```bash
["Custom Secret"]="mysecret_[0-9]{10}"
```

### Removing Patterns

Delete or comment out the line for the pattern you want to disable.

### Changing .gitignore Patterns

The installer adds patterns to `.gitignore` only if they aren't already present. You can manually edit `.gitignore` afterward.

## Integration with Existing Pre‑commit Hooks

If you already have a pre‑commit hook, you can merge the secret‑scanning logic into it. The template is a standalone Bash script that can be sourced or inlined.

## Limitations

- The regex patterns are simple and may produce false positives (e.g., a fictional API key in a novel).
- They may also miss secrets that don't match the provided patterns (e.g., custom JWT tokens).
- The hook only checks staged files; secrets already committed in the repository's history are not removed.
- It runs locally; for team‑wide enforcement, consider using a server‑side hook or a tool like [`truffleHog`](https://github.com/trufflesecurity/trufflehog).

## Unclear Parts / TODO

- The installer script assumes it's being run from within the `nova‑scripts` repository (it uses `SCRIPT_DIR` to locate the template). If you move the template elsewhere, you'll need to adjust the path.
- The hook does not scan binary files; it relies on `grep` which may skip them.

## Related Files

- `scripts/git-security/install-hooks.sh` – installation script.
- `scripts/git-security/pre-commit-template` – the hook template.

---

*Made with 💜 by NOVA*