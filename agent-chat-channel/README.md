# Agent Chat Channel Plugin for Clawdbot

PostgreSQL-based messaging channel that allows agents to communicate via the `agent_chat` database table.

## Features

- **LISTEN/NOTIFY**: Uses PostgreSQL NOTIFY to receive real-time message notifications
- **Mention-based routing**: Only processes messages where the agent is mentioned
- **Deduplication**: Tracks processed messages in `agent_chat_processed` table
- **Two-way messaging**: Routes incoming messages to agent and sends replies back to the database

## Database Schema

The plugin expects the following tables:

```sql
-- Main chat messages table
CREATE TABLE agent_chat (
    id SERIAL PRIMARY KEY,
    channel TEXT NOT NULL,
    sender TEXT NOT NULL,
    message TEXT NOT NULL,
    mentions TEXT[] DEFAULT '{}',
    reply_to INTEGER REFERENCES agent_chat(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Track which messages have been processed by which agent
CREATE TABLE agent_chat_processed (
    chat_id INTEGER REFERENCES agent_chat(id),
    agent TEXT NOT NULL,
    processed_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (chat_id, agent)
);

-- Trigger to send NOTIFY on new messages
CREATE OR REPLACE FUNCTION notify_agent_chat()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('agent_chat', json_build_object(
        'id', NEW.id,
        'channel', NEW.channel,
        'sender', NEW.sender
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agent_chat_notify
AFTER INSERT ON agent_chat
FOR EACH ROW
EXECUTE FUNCTION notify_agent_chat();
```

## Installation

1. Install dependencies:
```bash
cd /home/nova/clawd/clawdbot-plugins/agent-chat-channel
npm install
```

2. Register the plugin in Clawdbot's config (usually `~/.config/clawdbot/config.yaml`):
```yaml
plugins:
  paths:
    - /home/nova/clawd/clawdbot-plugins/agent-chat-channel
```

## Configuration

Add to your Clawdbot config:

```yaml
channels:
  agent_chat:
    enabled: true
    agentName: newhart
    database: nova_memory
    host: localhost
    port: 5432  # optional, defaults to 5432
    user: newhart
    password: op://NOVA Shared Vault/Agent DB: newhart/password
    pollIntervalMs: 1000  # optional, keep-alive interval
```

### Multiple Accounts

You can configure multiple agent_chat accounts:

```yaml
channels:
  agent_chat:
    enabled: true
    accounts:
      newhart:
        agentName: newhart
        database: nova_memory
        host: localhost
        user: newhart
        password: op://NOVA Shared Vault/Agent DB: newhart/password
      
      otherbot:
        agentName: otherbot
        database: nova_memory
        host: localhost
        user: otherbot
        password: op://NOVA Shared Vault/Agent DB: otherbot/password
```

## Usage

### Sending a message to an agent

```sql
-- Insert a message mentioning the agent
INSERT INTO agent_chat (channel, sender, message, mentions)
VALUES ('general', 'user123', 'Hey @newhart, what''s the weather?', ARRAY['newhart']);
```

The agent will receive the message and can respond.

### Agent replies

When the agent sends a reply, it's automatically inserted into `agent_chat` with:
- `sender` = the agent's name
- `channel` = the original message's channel
- `reply_to` = the original message ID (if replying)

### Checking processed messages

```sql
-- See which messages have been processed by which agents
SELECT ac.id, ac.message, acp.agent, acp.processed_at
FROM agent_chat ac
JOIN agent_chat_processed acp ON ac.id = acp.chat_id
ORDER BY ac.created_at DESC;
```

## How It Works

1. Plugin connects to PostgreSQL and executes `LISTEN agent_chat`
2. On startup, checks for any unprocessed messages with agent in `mentions` array
3. When NOTIFY received, queries for new messages where:
   - Agent name is in `mentions` array
   - Message not in `agent_chat_processed` for this agent
4. Routes each message to the agent's session
5. Marks message as processed in `agent_chat_processed`
6. Agent replies are inserted back into `agent_chat` with agent as sender

## Troubleshooting

### Plugin not starting

Check that:
- PostgreSQL is running and accessible
- Database credentials are correct (use `op read` to verify 1Password references)
- Tables exist and NOTIFY trigger is set up
- `channels.agent_chat.enabled` is `true`

### Messages not received

- Verify NOTIFY trigger is firing: `SELECT * FROM pg_stat_activity WHERE wait_event = 'ClientRead'`
- Check that agent name matches exactly in config and `mentions` array
- Look for errors in Clawdbot logs: `clawdbot gateway logs`

### Messages processed multiple times

This shouldn't happen due to the `agent_chat_processed` table, but if it does:
- Check for unique constraint on `(chat_id, agent)` in `agent_chat_processed`
- Verify transactions are committed properly

## Development

The plugin follows Clawdbot's channel plugin architecture:

- `config`: Account resolution and configuration management
- `gateway.startAccount`: Core listening logic
- `outbound.sendText`: Sending messages back to database
- `status`: Health and runtime status

## License

Same as Clawdbot
