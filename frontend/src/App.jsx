import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Clock, CheckCircle2, AlertCircle } from 'lucide-react';
import './index.css';

const API_URL = import.meta.env.VITE_API_URL || 'https://ai-query-agent.onrender.com';

function App() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: 'Hello! I am the AI Query Agent for your ERP system. You can ask me questions about students, teachers, attendance, or assignments in natural language.',
      timestamp: new Date().toISOString()
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userAsk = input.trim();
    setInput('');
    
    // Add user message
    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: userAsk,
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/v1/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: userAsk }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Something went wrong');
      }

      setMessages(prev => [...prev, {
        id: Date.now(),
        role: 'assistant',
        content: data.answer,
        executionTime: data.execution_time_ms,
        totalResults: data.total_results,
        query: data.generated_query,
        timestamp: new Date().toISOString()
      }]);

    } catch (error) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        role: 'assistant',
        error: true,
        content: `Sorry, I encountered an error: ${error.message}`,
        timestamp: new Date().toISOString()
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header className="header">
        <div className="icon-container">
          <Bot size={24} color="white" />
        </div>
        <div>
          <h1>AI Query Agent</h1>
          <p>ERP Database Assistant (GPT-5.2 Powered)</p>
        </div>
      </header>

      <div className="chat-container">
        {messages.map((m) => (
          <div key={m.id} className={`message-wrapper ${m.role === 'user' ? 'message-user' : 'message-ai'}`}>
            <div className="message-meta" style={{ justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
              {m.role === 'assistant' && <div className="avatar"><Bot size={14} /></div>}
              <span>{m.role === 'user' ? 'You' : 'Agent'}</span>
              <span>•</span>
              <span>{new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              {m.role === 'user' && <div className="avatar"><User size={14} /></div>}
            </div>

            <div className={`message-bubble ${m.role === 'user' ? 'user-bubble' : 'ai-bubble'}`}>
              <div style={{ whiteSpace: 'pre-wrap' }}>
                {m.error && <AlertCircle size={16} color="#ef4444" style={{ display: 'inline', marginRight: 8, verticalAlign: 'text-bottom' }}/>}
                {m.content}
              </div>
              
              {m.query && (
                <details style={{ marginTop: 12, fontSize: '0.85rem' }}>
                  <summary style={{ cursor: 'pointer', color: 'var(--accent-secondary)' }}>View generated query</summary>
                  <pre>
                    <code>{JSON.stringify(m.query, null, 2)}</code>
                  </pre>
                </details>
              )}

              {m.executionTime && (
                <div className="execution-time">
                  <CheckCircle2 size={12} color="#10b981" />
                  <span>Found {m.totalResults} result(s) in {m.executionTime.toFixed(0)} ms</span>
                </div>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="message-wrapper message-ai">
             <div className="message-meta">
              <div className="avatar"><Bot size={14} /></div>
              <span>Agent</span>
            </div>
            <div className="typing-indicator">
              <div className="dot"></div>
              <div className="dot"></div>
              <div className="dot"></div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        <div className="input-container">
          <textarea
            className="chat-input"
            rows="1"
            placeholder="Ask about students, attendance, or assignments..."
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = 'auto';
              e.target.style.height = e.target.scrollHeight + 'px';
            }}
            onKeyDown={handleKeyDown}
          />
          <button 
            className="send-button"
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
          >
            <Send size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;
