/* AI Chat Bubble Logic */
(function() {
    const N8N_WEBHOOK_URL = 'https://badrothman9990.app.n8n.cloud/webhook/da8be8e2-ab52-4f05-b372-b199ddc4da2a/chat';
    const POP_SOUND_URL = 'https://assets.mixkit.co/active_storage/sfx/2358/2358-preview.mp3'; // Fast pop/notification sound

    document.addEventListener('DOMContentLoaded', () => {
        // Create HTML structure if not exists
        const chatHTML = `
            <div class="chat-widget-container">
                <div class="chat-window" id="chatWindow">
                    <div class="chat-header">
                        <div class="chat-header-info">
                            <div class="chat-avatar"><i class="fas fa-robot"></i></div>
                            <div class="chat-header-text">
                                <h4>المساعد الذكي</h4>
                                <span>متصل الآن</span>
                            </div>
                        </div>
                        <div class="close-chat" id="closeChat"><i class="fas fa-times"></i></div>
                    </div>
                    <div class="chat-messages" id="chatMessages">
                        <div class="message bot">مرحباً بك! كيف يمكنني مساعدتك اليوم في الركن الأوسط للعقارات؟</div>
                    </div>
                    <div class="chat-input-area">
                        <input type="text" class="chat-input" id="chatInput" placeholder="اكتب رسالتك هنا..." />
                        <button class="send-btn" id="sendBtn"><i class="fas fa-paper-plane"></i></button>
                    </div>
                </div>
                <div class="chat-bubble" id="chatBubble">
                    <i class="fas fa-comment-dots"></i>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', chatHTML);

        const bubble = document.getElementById('chatBubble');
        const window = document.getElementById('chatWindow');
        const closeBtn = document.getElementById('closeChat');
        const input = document.getElementById('chatInput');
        const sendBtn = document.getElementById('sendBtn');
        const messagesContainer = document.getElementById('chatMessages');

        // Initial delay
        setTimeout(() => {
            bubble.classList.add('visible');
            const audio = new Audio(POP_SOUND_URL);
            audio.play().catch(e => console.log('Audio play prevented by browser policy. User interaction required.'));
        }, 5000);

        // Toggle chat
        bubble.addEventListener('click', () => {
            window.classList.toggle('open');
            if (window.classList.contains('open') && window.innerWidth > 768) {
                input.focus();
            }
        });

        closeBtn.addEventListener('click', () => {
            window.classList.remove('open');
        });

        // Send logic
        const sendMessage = async () => {
            const text = input.value.trim();
            if (!text) return;

            // Add user message to UI
            addMessage(text, 'user');
            input.value = '';

            // Loading state
            const loadingMsg = addMessage('...', 'bot');

            try {
                const response = await fetch(N8N_WEBHOOK_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        chatInput: text, 
                        message: text, 
                        sessionId: getSessionId() 
                    })
                });

                const data = await response.json();
                
                // Remove loading
                loadingMsg.remove();

                // Handle n8n response (usually 'output' or 'response' depending on workflow)
                const botReply = data.output || data.response || data.message || "عذراً، حدث خطأ في معالجة طلبك.";
                addMessage(botReply, 'bot');

            } catch (error) {
                loadingMsg.remove();
                addMessage("عذراً، لا يمكنني الاتصال بالخادم حالياً.", 'bot');
                console.error('Chat error:', error);
            }
        };

        const addMessage = (text, sender) => {
            const msgDiv = document.createElement('div');
            msgDiv.className = `message ${sender}`;
            msgDiv.innerText = text;
            messagesContainer.appendChild(msgDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            return msgDiv;
        };

        const getSessionId = () => {
            let sid = localStorage.getItem('chat_session_id');
            if (!sid) {
                sid = 'session_' + Math.random().toString(36).substr(2, 9);
                localStorage.setItem('chat_session_id', sid);
            }
            return sid;
        };

        sendBtn.addEventListener('click', sendMessage);
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
    });
})();
