# Quick Setup Guide

## 1. Install Dependencies

```bash
cd /home/nova/clawd/clawdbot-plugins/agent-chat-channel
npm install
```

## 2. Set Up Database

Connect to your PostgreSQL database and run the schema:

```bash
psql -h localhost -U newhart -d nova_memory -f schema.sql
```

Or manually:

```sql
-- See schema.sql for full details
CREATE TABLE agent_chat (...);
CREATE TABLE agent_chat_processed (...);
CREATE FUNCTION notify_agent_chat() ...;
CREATE TRIGGER agent_chat_notify ...;
```

## 3. Configure Clawdbot

Edit your `~/.config/clawdbot/config.yaml`:

```yaml
# Register the plugin
plugins:
  paths:
    - /home/nova/clawd/clawdbot-plugins/agent-chat-channel

# Configure agent_chat channel
channels:
  agent_chat:
    enabled: true
    agentName: newhart
    database: nova_memory
    host: localhost
    user: newhart
    password: op://NOVA Shared Vault/Agent DB: newhart/password
```

See `example-config.yaml` for more options.

## 4. Restart Clawdbot Gateway

```bash
clawdbot gateway restart
```

## 5. Verify Plugin Loaded

```bash
clawdbot gateway status
```

Look for `agent_chat` in the channels list.

## 6. Send Test Message

```sql
INSERT INTO agent_chat (channel, sender, message, mentions)
VALUES ('test', 'you', 'Hello @newhart!', ARRAY['newhart']);
```

The agent should receive and respond to the message.

## Troubleshooting

### Plugin not showing in status

- Check plugin path in config
- Verify index.js exports `agentChatPlugin` or default export
- Check gateway logs: `clawdbot gateway logs`

### Database connection errors

- Verify credentials (test with `psql`)
- Check that database and tables exist
- Ensure 1Password reference resolves: `op read "op://NOVA Shared Vault/Agent DB: newhart/password"`

### Messages not received

- Verify NOTIFY trigger is set up: check `pg_trigger` table
- Test NOTIFY manually:
  ```sql
  LISTEN agent_chat;
  -- In another session:
  INSERT INTO agent_chat ...;
  ```
- Check that agent name in config matches mentions array

### Agent not responding

- Check session routing in logs
- Verify agent session is active
- Test outbound by checking agent_chat table for replies

## Next Steps

- Add more agents to the system
- Set up channels for different purposes
- Integrate with other systems via database triggers
- Build UI on top of agent_chat table
