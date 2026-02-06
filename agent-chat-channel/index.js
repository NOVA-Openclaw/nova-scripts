import pg from 'pg';
const { Client } = pg;

/**
 * Agent Chat Channel Plugin for Clawdbot
 * 
 * Listens to PostgreSQL NOTIFY on 'agent_chat' channel and routes messages
 * to the agent when mentioned. Marks processed messages in agent_chat_processed.
 */

const PLUGIN_ID = 'agent_chat';

/**
 * Resolve agent_chat account config from Clawdbot config
 */
function resolveAgentChatAccount({ cfg, accountId = 'default' }) {
  const channelConfig = cfg.channels?.agent_chat;
  
  if (!channelConfig) {
    return {
      accountId,
      enabled: false,
      configured: false,
      config: {},
    };
  }

  const config = accountId === 'default' 
    ? channelConfig 
    : channelConfig.accounts?.[accountId] || {};

  return {
    accountId,
    name: config.name || accountId,
    enabled: config.enabled !== false,
    configured: Boolean(
      config.agentName &&
      config.database &&
      config.host &&
      config.user &&
      config.password
    ),
    config: {
      agentName: config.agentName,
      database: config.database,
      host: config.host,
      port: config.port || 5432,
      user: config.user,
      password: config.password,
      pollIntervalMs: config.pollIntervalMs || 1000,
    },
  };
}

/**
 * Create PostgreSQL client from config
 */
function createPgClient(config) {
  return new Client({
    host: config.host,
    port: config.port,
    database: config.database,
    user: config.user,
    password: config.password,
  });
}

/**
 * Fetch unprocessed messages for this agent from agent_chat table
 */
async function fetchUnprocessedMessages(client, agentName) {
  // Case-insensitive matching for agent mentions
  const query = `
    SELECT ac.id, ac.channel, ac.sender, ac.message, ac.mentions, ac.reply_to, ac.created_at
    FROM agent_chat ac
    LEFT JOIN agent_chat_processed acp ON ac.id = acp.chat_id AND LOWER(acp.agent) = LOWER($1)
    WHERE LOWER($1) = ANY(SELECT LOWER(unnest(ac.mentions)))
      AND acp.chat_id IS NULL
    ORDER BY ac.created_at ASC
  `;
  
  const result = await client.query(query, [agentName]);
  return result.rows;
}

/**
 * Mark message as processed
 */
async function markMessageProcessed(client, chatId, agentName) {
  // Store agent name lowercase for consistency
  const query = `
    INSERT INTO agent_chat_processed (chat_id, agent, processed_at)
    VALUES ($1, LOWER($2), NOW())
    ON CONFLICT (chat_id, agent) DO NOTHING
  `;
  
  await client.query(query, [chatId, agentName]);
}

/**
 * Insert outbound message into agent_chat
 */
async function insertOutboundMessage(client, { channel, sender, message, replyTo }) {
  const query = `
    INSERT INTO agent_chat (channel, sender, message, mentions, reply_to, created_at)
    VALUES ($1, $2, $3, $4, $5, NOW())
    RETURNING id
  `;
  
  const result = await client.query(query, [
    channel,
    sender,
    message,
    [], // mentions - empty for now, could be parsed from message
    replyTo || null,
  ]);
  
  return result.rows[0];
}

/**
 * Build session label for agent_chat message
 */
function buildSessionLabel({ channel, sender, chatId }) {
  return `${PLUGIN_ID}:${channel}:${sender}:${chatId}`;
}

/**
 * Start monitoring agent_chat for this account
 */
async function startAgentChatMonitor({ account, cfg, runtime, abortSignal, log }) {
  const { agentName, database, host, port, user, password, pollIntervalMs } = account.config;
  
  log?.info(`[agent_chat:${account.accountId}] Starting monitor for agent: ${agentName} @ ${host}:${port}/${database}`);
  
  const client = createPgClient(account.config);
  
  try {
    await client.connect();
    log?.info(`[agent_chat:${account.accountId}] Connected to PostgreSQL`);
    
    // Listen to agent_chat channel
    await client.query('LISTEN agent_chat');
    log?.info(`[agent_chat:${account.accountId}] Listening on channel 'agent_chat'`);
    
    // Handle notifications
    client.on('notification', async (msg) => {
      if (msg.channel === 'agent_chat') {
        log?.debug(`[agent_chat:${account.accountId}] Received notification`);
        
        try {
          const messages = await fetchUnprocessedMessages(client, agentName);
          
          for (const message of messages) {
            log?.info(`[agent_chat:${account.accountId}] Processing message ${message.id} from ${message.sender}`);
            
            // Build session label
            const sessionLabel = buildSessionLabel({
              channel: message.channel,
              sender: message.sender,
              chatId: message.id,
            });
            
            // Route to agent via runtime.handleInbound
            if (runtime?.handleInbound) {
              await runtime.handleInbound({
                channel: PLUGIN_ID,
                accountId: account.accountId,
                sessionLabel,
                sender: {
                  id: message.sender,
                  name: message.sender,
                },
                message: {
                  id: String(message.id),
                  text: message.message,
                  timestamp: new Date(message.created_at),
                  replyTo: message.reply_to ? String(message.reply_to) : undefined,
                },
                chatType: 'direct', // Could be enhanced to detect group chats
                metadata: {
                  channel: message.channel,
                  mentions: message.mentions,
                  dbId: message.id,
                },
              });
            }
            
            // Mark as processed
            await markMessageProcessed(client, message.id, agentName);
            log?.debug(`[agent_chat:${account.accountId}] Marked message ${message.id} as processed`);
          }
        } catch (error) {
          log?.error(`[agent_chat:${account.accountId}] Error processing notification:`, error);
        }
      }
    });
    
    // Initial check for existing unprocessed messages
    const initialMessages = await fetchUnprocessedMessages(client, agentName);
    log?.info(`[agent_chat:${account.accountId}] Found ${initialMessages.length} unprocessed messages on startup`);
    
    for (const message of initialMessages) {
      const sessionLabel = buildSessionLabel({
        channel: message.channel,
        sender: message.sender,
        chatId: message.id,
      });
      
      if (runtime?.handleInbound) {
        await runtime.handleInbound({
          channel: PLUGIN_ID,
          accountId: account.accountId,
          sessionLabel,
          sender: {
            id: message.sender,
            name: message.sender,
          },
          message: {
            id: String(message.id),
            text: message.message,
            timestamp: new Date(message.created_at),
            replyTo: message.reply_to ? String(message.reply_to) : undefined,
          },
          chatType: 'direct',
          metadata: {
            channel: message.channel,
            mentions: message.mentions,
            dbId: message.id,
          },
        });
      }
      
      await markMessageProcessed(client, message.id, agentName);
    }
    
    // Keep connection alive
    const keepAliveInterval = setInterval(() => {
      if (!abortSignal?.aborted) {
        client.query('SELECT 1').catch((err) => {
          log?.error(`[agent_chat:${account.accountId}] Keep-alive failed:`, err);
        });
      }
    }, pollIntervalMs);
    
    // Handle abort signal
    if (abortSignal) {
      abortSignal.addEventListener('abort', async () => {
        log?.info(`[agent_chat:${account.accountId}] Received abort signal`);
        clearInterval(keepAliveInterval);
        try {
          await client.query('UNLISTEN agent_chat');
          await client.end();
          log?.info(`[agent_chat:${account.accountId}] Disconnected from PostgreSQL`);
        } catch (error) {
          log?.error(`[agent_chat:${account.accountId}] Error during shutdown:`, error);
        }
      });
    }
    
    // Wait for abort
    return new Promise((resolve) => {
      if (abortSignal) {
        abortSignal.addEventListener('abort', () => resolve());
      }
    });
    
  } catch (error) {
    log?.error(`[agent_chat:${account.accountId}] Fatal error:`, error);
    try {
      await client.end();
    } catch (cleanupError) {
      // Ignore cleanup errors
    }
    throw error;
  }
}

/**
 * Agent Chat Channel Plugin
 */
export const agentChatPlugin = {
  id: PLUGIN_ID,
  
  meta: {
    name: 'Agent Chat',
    description: 'PostgreSQL-based agent messaging via agent_chat table',
    order: 999, // Low priority in channel list
  },
  
  capabilities: {
    chatTypes: ['direct', 'group'],
    media: false,
    reactions: false,
    threads: false,
  },
  
  reload: {
    configPrefixes: ['channels.agent_chat'],
  },
  
  config: {
    listAccountIds: (cfg) => {
      const channelConfig = cfg.channels?.agent_chat;
      if (!channelConfig) return [];
      
      const accounts = ['default'];
      if (channelConfig.accounts) {
        accounts.push(...Object.keys(channelConfig.accounts));
      }
      return accounts;
    },
    
    resolveAccount: (cfg, accountId) => resolveAgentChatAccount({ cfg, accountId }),
    
    defaultAccountId: () => 'default',
    
    isConfigured: (account) => account.configured,
    
    describeAccount: (account) => ({
      accountId: account.accountId,
      name: account.name,
      enabled: account.enabled,
      configured: account.configured,
      agentName: account.config.agentName,
      database: account.config.database,
      host: account.config.host,
    }),
  },
  
  outbound: {
    deliveryMode: 'direct',
    
    sendText: async ({ cfg, to, text, accountId, metadata }) => {
      const account = resolveAgentChatAccount({ cfg, accountId });
      
      if (!account.configured) {
        throw new Error(`agent_chat account ${accountId} not configured`);
      }
      
      const client = createPgClient(account.config);
      
      try {
        await client.connect();
        
        // Extract channel and reply_to from metadata or 'to' parameter
        const channel = metadata?.channel || 'default';
        const replyTo = metadata?.replyTo || null;
        
        const result = await insertOutboundMessage(client, {
          channel,
          sender: account.config.agentName,
          message: text,
          replyTo,
        });
        
        return {
          channel: PLUGIN_ID,
          messageId: String(result.id),
          success: true,
        };
      } finally {
        await client.end();
      }
    },
  },
  
  gateway: {
    startAccount: async (ctx) => {
      const account = ctx.account;
      
      return await startAgentChatMonitor({
        account,
        cfg: ctx.cfg,
        runtime: ctx.runtime,
        abortSignal: ctx.abortSignal,
        log: ctx.log,
      });
    },
  },
  
  status: {
    defaultRuntime: {
      accountId: 'default',
      running: false,
      lastStartAt: null,
      lastStopAt: null,
      lastError: null,
    },
    
    buildChannelSummary: ({ snapshot }) => ({
      configured: snapshot.configured ?? false,
      running: snapshot.running ?? false,
      agentName: snapshot.agentName ?? null,
      database: snapshot.database ?? null,
    }),
    
    buildAccountSnapshot: ({ account, runtime }) => ({
      accountId: account.accountId,
      name: account.name,
      enabled: account.enabled,
      configured: account.configured,
      agentName: account.config.agentName,
      database: account.config.database,
      running: runtime?.running ?? false,
      lastStartAt: runtime?.lastStartAt ?? null,
      lastStopAt: runtime?.lastStopAt ?? null,
      lastError: runtime?.lastError ?? null,
    }),
  },
};

// Default export for plugin loader
export default agentChatPlugin;
