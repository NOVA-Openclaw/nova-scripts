-- Agent Chat Database Schema
-- 
-- This file sets up the tables and triggers needed for the agent_chat channel plugin.
-- Run this in your PostgreSQL database (e.g., nova_memory).

-- Main chat messages table
CREATE TABLE IF NOT EXISTS agent_chat (
    id SERIAL PRIMARY KEY,
    channel TEXT NOT NULL DEFAULT 'default',
    sender TEXT NOT NULL,
    message TEXT NOT NULL,
    mentions TEXT[] DEFAULT '{}',
    reply_to INTEGER REFERENCES agent_chat(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Track which messages have been processed by which agent
CREATE TABLE IF NOT EXISTS agent_chat_processed (
    chat_id INTEGER REFERENCES agent_chat(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    processed_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (chat_id, agent)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_agent_chat_mentions ON agent_chat USING GIN(mentions);
CREATE INDEX IF NOT EXISTS idx_agent_chat_created_at ON agent_chat(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_chat_channel ON agent_chat(channel);
CREATE INDEX IF NOT EXISTS idx_agent_chat_processed_agent ON agent_chat_processed(agent);

-- Function to send NOTIFY when new message arrives
CREATE OR REPLACE FUNCTION notify_agent_chat()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('agent_chat', json_build_object(
        'id', NEW.id,
        'channel', NEW.channel,
        'sender', NEW.sender,
        'mentions', NEW.mentions
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to call notify function on INSERT
DROP TRIGGER IF EXISTS agent_chat_notify ON agent_chat;
CREATE TRIGGER agent_chat_notify
AFTER INSERT ON agent_chat
FOR EACH ROW
EXECUTE FUNCTION notify_agent_chat();

-- Example: Insert a test message
-- INSERT INTO agent_chat (channel, sender, message, mentions)
-- VALUES ('general', 'test_user', 'Hello @newhart!', ARRAY['newhart']);
