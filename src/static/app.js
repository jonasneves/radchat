/**
 * RadChat - Duke Radiology Assistant
 * Frontend Application
 */

class RadChat {
    constructor() {
        this.sessionId = this.generateSessionId();
        this.isStreaming = false;

        // DOM Elements
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.inputForm = document.getElementById('inputForm');
        this.sendBtn = document.getElementById('sendBtn');
        this.modelSelect = document.getElementById('modelSelect');
        this.modelBtn = document.getElementById('modelBtn');
        this.modelMenu = document.getElementById('modelMenu');
        this.modelOptions = document.getElementById('modelOptions');
        this.modelNameEl = document.getElementById('modelName');
        this.shiftIndicator = document.getElementById('shiftIndicator');
        this.welcomeState = document.getElementById('welcomeState');
        this.quickActions = document.getElementById('quickActions');

        this.selectedModel = { id: 'openai/gpt-4o-mini', name: 'GPT-4o Mini' };
        this.user = null;

        // Auth elements
        this.authArea = document.getElementById('authArea');
        this.loginBtn = document.getElementById('loginBtn');

        // Scroll tracking
        this.lastMessageDate = null;
        this.scrollToBottomBtn = null;
        this.isNearBottom = true;

        // Carousel
        this.carouselTrack = document.getElementById('carouselTrack');
        this.carouselPrev = document.getElementById('carouselPrev');
        this.carouselNext = document.getElementById('carouselNext');
        this.carouselDots = document.getElementById('carouselDots');
        this.currentPage = 0;
        this.totalPages = 0;

        // Thinking indicator timing
        this.thinkingShownAt = null;
        this.minThinkingTime = 800; // minimum ms to show indicator

        this.init();
    }

    generateSessionId() {
        return 'session_' + Math.random().toString(36).substring(2, 15);
    }

    async init() {
        this.bindEvents();
        this.initCarousel();
        await this.checkAuthStatus();
        await this.loadModels();
        this.updateShiftIndicator();
        setInterval(() => this.updateShiftIndicator(), 60000);

        // Listen for auth popup messages
        window.addEventListener('message', async (e) => {
            if (e.data?.type === 'duke_auth' && e.data?.success) {
                await this.checkAuthStatus();
            }
        });
    }

    bindEvents() {
        this.inputForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Quick action buttons
        document.querySelectorAll('.quick-action').forEach(btn => {
            btn.addEventListener('click', () => {
                const query = btn.dataset.query;
                this.messageInput.value = query;
                this.sendMessage();
            });
        });

        // Global keyboard listener - focus input when typing anywhere
        document.addEventListener('keydown', (e) => {
            // Skip if already focused on an input/textarea/select
            const activeEl = document.activeElement;
            if (activeEl.tagName === 'INPUT' ||
                activeEl.tagName === 'TEXTAREA' ||
                activeEl.tagName === 'SELECT') {
                return;
            }

            // Skip modifier keys and special keys
            if (e.metaKey || e.ctrlKey || e.altKey) return;
            if (e.key.length !== 1 && e.key !== 'Backspace') return;

            // Focus the input and let the keypress go through
            this.messageInput.focus();
        });

        // Model menu toggle
        this.modelBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.modelMenu.classList.toggle('open');
            this.modelBtn.classList.toggle('active');
        });

        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!this.modelMenu.contains(e.target) && e.target !== this.modelBtn) {
                this.modelMenu.classList.remove('open');
                this.modelBtn.classList.remove('active');
            }
        });

        // Scroll tracking for "new messages" button
        this.chatMessages.addEventListener('scroll', () => {
            const { scrollTop, scrollHeight, clientHeight } = this.chatMessages;
            this.isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
            this.updateScrollToBottomButton();
        });

        // Brand title click - start new chat
        const brandTitle = document.getElementById('brandTitle');
        if (brandTitle) {
            brandTitle.addEventListener('click', () => this.startNewChat());
        }
    }

    startNewChat() {
        // Generate new session
        this.sessionId = this.generateSessionId();

        // Clear messages from DOM
        const messages = this.chatMessages.querySelectorAll('.message, .date-group-header, .thinking-indicator');
        messages.forEach(el => el.remove());

        // Reset state
        this.lastMessageDate = null;
        this.isStreaming = false;

        // Show welcome state
        if (this.welcomeState) {
            this.welcomeState.style.display = '';
        }

        // Update welcome message
        this.updateWelcomeMessage();

        // Focus input
        this.messageInput.focus();
    }

    updateScrollToBottomButton() {
        const hasMessages = this.chatMessages.querySelectorAll('.message').length > 0;

        if (!this.isNearBottom && hasMessages) {
            if (!this.scrollToBottomBtn) {
                this.scrollToBottomBtn = document.createElement('button');
                this.scrollToBottomBtn.className = 'scroll-to-bottom';
                this.scrollToBottomBtn.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                        <path d="M12 5v14M5 12l7 7 7-7"/>
                    </svg>
                    New messages
                `;
                this.scrollToBottomBtn.addEventListener('click', () => this.scrollToBottom());
                this.chatMessages.parentElement.appendChild(this.scrollToBottomBtn);
            }
        } else if (this.scrollToBottomBtn) {
            this.scrollToBottomBtn.remove();
            this.scrollToBottomBtn = null;
        }
    }

    initCarousel() {
        if (!this.carouselTrack) return;

        const pages = this.carouselTrack.querySelectorAll('.carousel-page');
        this.totalPages = pages.length;

        if (this.totalPages <= 1) {
            // Hide arrows if only one page
            if (this.carouselPrev) this.carouselPrev.style.display = 'none';
            if (this.carouselNext) this.carouselNext.style.display = 'none';
            if (this.carouselDots) this.carouselDots.style.display = 'none';
            return;
        }

        // Bind arrow events
        if (this.carouselPrev) {
            this.carouselPrev.addEventListener('click', () => this.goToPage(this.currentPage - 1));
        }
        if (this.carouselNext) {
            this.carouselNext.addEventListener('click', () => this.goToPage(this.currentPage + 1));
        }

        // Bind dot events
        if (this.carouselDots) {
            this.carouselDots.querySelectorAll('.carousel-dot').forEach(dot => {
                dot.addEventListener('click', () => {
                    const page = parseInt(dot.dataset.page, 10);
                    this.goToPage(page);
                });
            });
        }

        this.updateCarouselState();
    }

    goToPage(page) {
        if (page < 0 || page >= this.totalPages) return;

        this.currentPage = page;

        // Slide the track
        this.carouselTrack.style.transform = `translateX(-${page * 100}%)`;

        // Update page visibility
        this.carouselTrack.querySelectorAll('.carousel-page').forEach((p, i) => {
            p.classList.toggle('active', i === page);
        });

        this.updateCarouselState();
    }

    updateCarouselState() {
        // Update arrows
        if (this.carouselPrev) {
            this.carouselPrev.disabled = this.currentPage === 0;
        }
        if (this.carouselNext) {
            this.carouselNext.disabled = this.currentPage === this.totalPages - 1;
        }

        // Update dots
        if (this.carouselDots) {
            this.carouselDots.querySelectorAll('.carousel-dot').forEach((dot, i) => {
                dot.classList.toggle('active', i === this.currentPage);
            });
        }
    }

    async loadModels() {
        try {
            const response = await fetch('/models');
            const data = await response.json();

            this.models = data.models;
            this.modelOptions.innerHTML = '';

            data.models.forEach((model, index) => {
                // Update hidden select
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.name;
                this.modelSelect.appendChild(option);

                // Create menu option
                const menuOption = document.createElement('div');
                menuOption.className = `model-option ${index === 0 ? 'selected' : ''}`;
                menuOption.dataset.id = model.id;
                menuOption.dataset.name = model.name;
                menuOption.innerHTML = `
                    <svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                        <polyline points="20 6 9 17 4 12"/>
                    </svg>
                    <span>${model.name}</span>
                `;
                menuOption.addEventListener('click', () => this.selectModel(model));
                this.modelOptions.appendChild(menuOption);
            });

            // Set default
            if (data.models.length > 0) {
                this.selectedModel = data.models[0];
                if (this.modelNameEl) {
                    this.modelNameEl.textContent = data.models[0].name;
                }
            }
        } catch (error) {
            console.error('Failed to load models:', error);
        }
    }

    selectModel(model) {
        this.selectedModel = model;
        this.modelSelect.value = model.id;

        // Update UI
        this.modelOptions.querySelectorAll('.model-option').forEach(opt => {
            opt.classList.toggle('selected', opt.dataset.id === model.id);
        });

        // Update button label
        if (this.modelNameEl) {
            this.modelNameEl.textContent = model.name;
        }

        // Close menu
        this.modelMenu.classList.remove('open');
        this.modelBtn.classList.remove('active');
    }

    async checkAuthStatus() {
        // Show cached state immediately to prevent flicker
        const cachedUser = localStorage.getItem('radchat_user');
        if (cachedUser) {
            try {
                this.user = JSON.parse(cachedUser);
                this.renderUserInfo();
                this.updateWelcomeMessage();
            } catch (e) {
                localStorage.removeItem('radchat_user');
            }
        }

        // Then verify with server
        try {
            const response = await fetch('/auth/status');
            const data = await response.json();

            if (data.authenticated && data.user) {
                this.user = data.user;
                localStorage.setItem('radchat_user', JSON.stringify(data.user));
                this.renderUserInfo();
            } else {
                this.user = null;
                localStorage.removeItem('radchat_user');
                this.renderLoginButton();
            }
        } catch (error) {
            console.error('Failed to check auth status:', error);
            // Keep cached state on network error, or show login if no cache
            if (!this.user) {
                this.renderLoginButton();
            }
        }
        this.updateWelcomeMessage();
    }

    updateWelcomeMessage() {
        if (!this.welcomeState) return;

        const heading = this.welcomeState.querySelector('h2');
        const subtext = this.welcomeState.querySelector('p');

        if (this.user) {
            const fullName = this.user.name || this.user.netid || 'User';
            const firstName = fullName.split(' ')[0];
            heading.textContent = `How can I help, ${firstName}?`;
            subtext.textContent = 'Use the quick actions below or type a message';
        } else {
            heading.textContent = 'Welcome to DukeRad Chat';
            subtext.textContent = 'Sign in with Duke to get started';
        }
    }

    renderLoginButton() {
        this.authArea.innerHTML = `
            <button class="login-btn" id="loginBtn">Sign in with Duke</button>
        `;
        this.authArea.querySelector('#loginBtn').addEventListener('click', () => this.login());
    }

    renderUserInfo() {
        const fullName = this.user.name || this.user.netid || 'User';
        const firstName = fullName.split(' ')[0];
        const initials = fullName.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();

        this.authArea.innerHTML = `
            <div class="user-info">
                <button class="user-btn" id="userBtn">
                    <div class="user-avatar">${initials}</div>
                    <span class="user-name">${firstName}</span>
                </button>
                <div class="user-menu" id="userMenu">
                    <button class="user-menu-item" disabled>${fullName}</button>
                    <button class="user-menu-item danger" id="logoutBtn">Sign out</button>
                </div>
            </div>
        `;

        const userBtn = this.authArea.querySelector('#userBtn');
        const userMenu = this.authArea.querySelector('#userMenu');

        userBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            userMenu.classList.toggle('open');
        });

        document.addEventListener('click', () => {
            userMenu.classList.remove('open');
        });

        this.authArea.querySelector('#logoutBtn').addEventListener('click', () => this.logout());
    }

    login() {
        const width = 500;
        const height = 600;
        const left = window.screenX + (window.outerWidth - width) / 2;
        const top = window.screenY + (window.outerHeight - height) / 2;

        window.open(
            '/auth/duke',
            'Duke Login',
            `width=${width},height=${height},left=${left},top=${top}`
        );
    }

    async logout() {
        try {
            await fetch('/auth/logout', { method: 'POST' });
            this.user = null;
            localStorage.removeItem('radchat_user');
            this.renderLoginButton();
            this.updateWelcomeMessage();
        } catch (error) {
            console.error('Logout failed:', error);
        }
    }

    updateShiftIndicator() {
        const now = new Date();
        const hour = now.getHours();
        const day = now.getDay();

        const isWeekend = day === 0 || day === 6;
        const isAfterHours = hour < 7 || (hour === 7 && now.getMinutes() < 30) || hour >= 17;
        const isBusinessHours = !isWeekend && !isAfterHours;

        const shiftText = this.shiftIndicator.querySelector('.shift-text');
        const timeStr = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });

        if (isBusinessHours) {
            shiftText.textContent = `${timeStr} - Business Hours`;
            this.shiftIndicator.classList.remove('after-hours');
        } else {
            shiftText.textContent = `${timeStr} - After Hours`;
            this.shiftIndicator.classList.add('after-hours');
        }
    }

    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isStreaming) return;

        // Check if authenticated
        if (!this.user) {
            this.showToast('Please sign in with your Duke NetID to use RadChat.');
            return;
        }

        // Hide welcome state
        if (this.welcomeState) {
            this.welcomeState.style.display = 'none';
        }

        // Add user message
        this.addMessage('user', message);
        this.messageInput.value = '';
        this.isStreaming = true;
        this.sendBtn.disabled = true;
        this.setQuickActionsDisabled(true);

        // Add assistant message with loading state
        const assistantMessage = this.addMessage('assistant', '', true);
        const contentWrapper = assistantMessage.querySelector('.message-content-wrapper');
        const cardsContainer = assistantMessage.querySelector('.message-cards');
        const bubbleEl = assistantMessage.querySelector('.message-bubble');
        let messageRevealed = false; // Track if we've shown the message yet

        try {
            const response = await fetch('/chat/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message,
                    session_id: this.sessionId,
                    model: this.modelSelect.value
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Request failed');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            let buffer = '';
            let toolResults = [];
            let usedTools = false;

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const data = line.slice(6);

                    if (data === '[DONE]') continue;

                    try {
                        const parsed = JSON.parse(data);
                        if (parsed.error) {
                            this.showToast(parsed.error, 'error');
                            bubbleEl.innerHTML = '<span class="error-text">Unable to get response. Please try again.</span>';
                            return;
                        }
                        if (parsed.text) {
                            buffer += parsed.text;

                            // Process buffer for tool markers
                            while (true) {
                                // Check for tool start marker
                                const startMatch = buffer.match(/__TOOL_START__(.+?)__/);
                                if (startMatch) {
                                    const beforeMarker = buffer.slice(0, startMatch.index);
                                    if (beforeMarker) {
                                        fullText += beforeMarker;
                                        bubbleEl.innerHTML = this.formatMessage(fullText);
                                    }
                                    // Hide loading message, show thinking indicator
                                    assistantMessage.style.display = 'none';
                                    this.addToolCallIndicator(startMatch[1]);
                                    buffer = buffer.slice(startMatch.index + startMatch[0].length);
                                    continue;
                                }

                                // Check for tool result marker
                                const resultMatch = buffer.match(/__TOOL_RESULT__(.+?)__/);
                                if (resultMatch) {
                                    buffer = buffer.slice(resultMatch.index + resultMatch[0].length);
                                    usedTools = true;
                                    // Always remove thinking indicator on tool result
                                    this.removeThinkingIndicator();
                                    // Show message (only once)
                                    if (!messageRevealed) {
                                        await this.showAssistantMessage(assistantMessage, bubbleEl, fullText);
                                        messageRevealed = true;
                                    }
                                    try {
                                        const toolData = JSON.parse(resultMatch[1]);
                                        toolResults.push(toolData);
                                        this.renderToolResult(cardsContainer, toolData);
                                    } catch (e) {
                                        console.error('Failed to parse tool result:', e);
                                    }
                                    continue;
                                }

                                // Stream text immediately if no marker could be starting
                                const underscoreIdx = buffer.indexOf('_');
                                if (underscoreIdx === -1) {
                                    // No underscore, safe to output all
                                    fullText += buffer;
                                    if (!messageRevealed) {
                                        await this.showAssistantMessage(assistantMessage, bubbleEl, fullText);
                                        messageRevealed = true;
                                    } else {
                                        bubbleEl.innerHTML = this.formatMessage(fullText);
                                    }
                                    buffer = '';
                                } else if (underscoreIdx > 0) {
                                    // Output everything before the underscore
                                    fullText += buffer.slice(0, underscoreIdx);
                                    if (!messageRevealed) {
                                        await this.showAssistantMessage(assistantMessage, bubbleEl, fullText);
                                        messageRevealed = true;
                                    } else {
                                        bubbleEl.innerHTML = this.formatMessage(fullText);
                                    }
                                    buffer = buffer.slice(underscoreIdx);
                                }
                                // else: buffer starts with '_', keep buffering
                                break;
                            }
                        }
                    } catch (e) {
                        // Skip invalid JSON
                    }
                }

                this.scrollToBottom();
            }

            // Process any remaining buffer
            if (buffer) {
                fullText += buffer;
            }

            // Final render - bubble is now just for text
            bubbleEl.innerHTML = this.formatMessage(fullText);
            this.parseAndRenderToolResults(bubbleEl, fullText);

            // Append any tool result cards that were rendered
            toolResults.forEach(tr => {
                const existingCard = cardsContainer.querySelector(`[data-tool="${tr.tool}"]`);
                if (!existingCard) {
                    this.renderToolResult(cardsContainer, tr);
                }
            });

            // Add message footer with time and source badge
            this.addMessageFooter(bubbleEl, usedTools);

        } catch (error) {
            bubbleEl.innerHTML = `<span style="color: #DC2626;">Error: ${error.message}</span>`;
        } finally {
            this.isStreaming = false;
            this.sendBtn.disabled = false;
            this.setQuickActionsDisabled(false);
            this.scrollToBottom();
        }
    }

    setQuickActionsDisabled(disabled) {
        document.querySelectorAll('.quick-action').forEach(btn => {
            btn.disabled = disabled;
        });
    }

    formatDateGroup(date) {
        const now = new Date();
        const messageDate = new Date(date);

        if (now.toDateString() === messageDate.toDateString()) {
            return 'Today';
        }

        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        if (yesterday.toDateString() === messageDate.toDateString()) {
            return 'Yesterday';
        }

        return messageDate.toLocaleDateString('en-US', {
            weekday: 'long',
            month: 'short',
            day: 'numeric'
        });
    }

    addDateGroupHeader(date) {
        const dateStr = this.formatDateGroup(date);

        // Check if we need a new header
        if (this.lastMessageDate === dateStr) {
            return;
        }

        this.lastMessageDate = dateStr;

        const headerEl = document.createElement('div');
        headerEl.className = 'date-group-header';
        headerEl.innerHTML = `<span>${dateStr}</span>`;
        this.chatMessages.appendChild(headerEl);
    }

    addMessage(role, content, isLoading = false) {
        // Add date group header if needed
        this.addDateGroupHeader(new Date());

        const messageEl = document.createElement('div');
        messageEl.className = `message ${role}`;
        messageEl.dataset.timestamp = Date.now();

        // Add avatar for assistant messages
        if (role === 'assistant') {
            const avatarEl = document.createElement('div');
            avatarEl.className = 'message-avatar';
            avatarEl.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
            `;
            messageEl.appendChild(avatarEl);

            // Create content wrapper (cards + bubble as siblings)
            const contentWrapper = document.createElement('div');
            contentWrapper.className = 'message-content-wrapper';

            // Cards container (outside bubble)
            const cardsContainer = document.createElement('div');
            cardsContainer.className = 'message-cards';
            contentWrapper.appendChild(cardsContainer);

            // Message bubble (text only)
            const bubbleEl = document.createElement('div');
            bubbleEl.className = 'message-bubble';
            if (isLoading) {
                bubbleEl.innerHTML = `
                    <div class="loading-spinner">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                            <circle cx="12" cy="12" r="10" stroke-opacity="0.25"/>
                            <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/>
                        </svg>
                    </div>
                `;
            } else {
                bubbleEl.innerHTML = this.formatMessage(content);
            }
            contentWrapper.appendChild(bubbleEl);

            messageEl.appendChild(contentWrapper);
        } else {
            // User message - simple bubble
            const bubbleEl = document.createElement('div');
            bubbleEl.className = 'message-bubble';
            if (isLoading) {
                bubbleEl.innerHTML = `
                    <div class="loading-spinner">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                            <circle cx="12" cy="12" r="10" stroke-opacity="0.25"/>
                            <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/>
                        </svg>
                    </div>
                `;
            } else {
                bubbleEl.innerHTML = this.formatMessage(content);
            }

            // Add status inside bubble for user messages
            const statusEl = document.createElement('div');
            statusEl.className = 'message-status';
            statusEl.innerHTML = `
                <span class="message-time">just now</span>
                <svg class="status-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="20 6 9 17 4 12"/>
                </svg>
            `;
            bubbleEl.appendChild(statusEl);

            // Simulate delivery status changes
            setTimeout(() => this.updateMessageStatus(messageEl, 'delivered'), 300);
            setTimeout(() => this.updateMessageStatus(messageEl, 'read'), 600);

            messageEl.appendChild(bubbleEl);
        }

        this.chatMessages.appendChild(messageEl);
        this.scrollToBottom();

        return messageEl;
    }

    updateMessageStatus(messageEl, status) {
        const statusEl = messageEl.querySelector('.message-status');
        if (!statusEl) return;

        const iconEl = statusEl.querySelector('.status-icon');
        if (!iconEl) return;

        if (status === 'delivered' || status === 'read') {
            // Double check mark
            iconEl.innerHTML = `<polyline points="18 6 7 17 2 12"/><polyline points="22 6 11 17 8 14"/>`;
        }
        if (status === 'read') {
            iconEl.classList.add('read');
        }
    }

    addMessageFooter(bubbleEl, usedTools = false) {
        const footer = document.createElement('div');
        footer.className = 'message-footer';

        if (usedTools) {
            footer.innerHTML = `
                <span class="source-badge verified">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                        <polyline points="22 4 12 14.01 9 11.01"/>
                    </svg>
                    Verified
                </span>
                <span class="message-time">just now</span>
            `;
        } else {
            footer.innerHTML = `
                <span class="source-badge unverified">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                    General knowledge
                </span>
                <span class="message-time">just now</span>
            `;
        }
        bubbleEl.appendChild(footer);
    }

    addToolCallIndicator(toolName) {
        // Remove any existing thinking indicator
        this.removeThinkingIndicator();

        // Record when indicator is shown
        this.thinkingShownAt = Date.now();

        // Format tool name for display
        const displayName = toolName.replace(/_/g, ' ').replace(/search |get /gi, '');

        // Choose icon based on tool type
        let iconSvg = `<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>`; // activity/pulse
        if (toolName.includes('contact') || toolName.includes('phone')) {
            iconSvg = `<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>`;
        } else if (toolName.includes('acr')) {
            iconSvg = `<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>`;
        }

        const indicator = document.createElement('div');
        indicator.className = 'thinking-indicator';
        indicator.innerHTML = `
            <div class="thinking-avatar">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
            </div>
            <div class="thinking-bubble">
                <svg class="thinking-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    ${iconSvg}
                </svg>
                <span class="thinking-text">Searching ${displayName}</span>
                <div class="thinking-dots">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        this.chatMessages.appendChild(indicator);
        this.scrollToBottom();
    }

    removeThinkingIndicator() {
        const indicator = this.chatMessages.querySelector('.thinking-indicator');
        if (indicator) indicator.remove();
    }

    async showAssistantMessage(messageEl, bubbleEl, text) {
        // Wait for minimum thinking time if indicator was recently shown
        if (this.thinkingShownAt) {
            const elapsed = Date.now() - this.thinkingShownAt;
            if (elapsed < this.minThinkingTime) {
                await new Promise(r => setTimeout(r, this.minThinkingTime - elapsed));
            }
            this.thinkingShownAt = null;
        }
        // Remove thinking indicator if present
        this.removeThinkingIndicator();
        // Show the message element
        messageEl.style.display = '';
        // Clear loading spinner from bubble
        const loadingSpinner = bubbleEl.querySelector('.loading-spinner');
        if (loadingSpinner) loadingSpinner.remove();
        // Render the text
        bubbleEl.innerHTML = this.formatMessage(text);
    }

    renderToolResult(cardsContainer, toolData) {
        const { type, tool, data } = toolData;

        // Don't render if there's an error
        if (data.error) return;

        if (type === 'contacts') {
            // Handle different response structures
            let contacts = [];
            if (data.results) {
                // search_phone_directory returns { results: [...] }
                contacts = data.results;
            } else if (data.contacts) {
                // get_scheduling_contact, list_contacts_by_type return { contacts: [...] }
                contacts = data.contacts;
            } else if (data.contact) {
                // get_reading_room_contact, get_procedure_contact return { contact: {...} }
                contacts = [data.contact];
                if (data.alternatives) {
                    contacts = contacts.concat(data.alternatives);
                }
            }

            if (contacts.length > 0) {
                const card = this.renderContactResults(contacts.slice(0, 5), data.time_context);
                card.dataset.tool = tool;
                cardsContainer.appendChild(card);
            }
        } else if (type === 'acr') {
            // Render ACR results
            const topics = data.topics || data.results || [];
            if (topics.length > 0) {
                // Search results - show list of topics
                const card = this.renderACRSearchResults(topics);
                card.dataset.tool = tool;
                cardsContainer.appendChild(card);
            } else if (data.topic || data.first_line_imaging) {
                // Recommendation results with detailed data
                const card = this.renderACRRecommendations(data);
                card.dataset.tool = tool;
                cardsContainer.appendChild(card);
            }
        }

        this.scrollToBottom();
    }

    renderACRSearchResults(topics) {
        const container = document.createElement('div');
        container.className = 'data-card';

        const header = document.createElement('div');
        header.className = 'data-card-header acr-header';
        header.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
            <span>ACR CRITERIA</span>
        `;
        container.appendChild(header);

        const body = document.createElement('div');
        body.className = 'data-card-body';

        topics.slice(0, 3).forEach(topic => {
            const item = document.createElement('div');
            item.className = 'acr-topic-item';
            item.innerHTML = `
                <a href="${topic.url || '#'}" target="_blank" rel="noopener noreferrer">
                    <span class="acr-topic-title">${topic.title || topic.name}</span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                        <polyline points="15 3 21 3 21 9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                </a>
            `;
            body.appendChild(item);
        });

        container.appendChild(body);
        return container;
    }

    renderACRRecommendations(data) {
        const container = document.createElement('div');
        container.className = 'data-card acr-card';

        // Header
        const header = document.createElement('div');
        header.className = 'data-card-header acr-header';
        header.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
            <span>ACR CRITERIA</span>
        `;
        container.appendChild(header);

        const body = document.createElement('div');
        body.className = 'data-card-body acr-body';

        // Topic title
        if (data.topic) {
            const topicEl = document.createElement('div');
            topicEl.className = 'acr-topic-header';
            topicEl.innerHTML = `
                <h4>${data.topic}</h4>
                ${data.url ? `<a href="${data.url}" target="_blank" rel="noopener noreferrer" class="acr-link">View full criteria →</a>` : ''}
            `;
            body.appendChild(topicEl);
        }

        // Recommendations sections
        if (data.first_line_imaging && data.first_line_imaging.length > 0) {
            body.appendChild(this.createACRSection('Usually Appropriate', data.first_line_imaging, 'appropriate'));
        }

        if (data.alternatives && data.alternatives.length > 0) {
            body.appendChild(this.createACRSection('May Be Appropriate', data.alternatives, 'maybe'));
        }

        if (data.usually_not_appropriate && data.usually_not_appropriate.length > 0) {
            body.appendChild(this.createACRSection('Usually Not Appropriate', data.usually_not_appropriate, 'not-appropriate'));
        }

        // If no detailed recommendations, show instructions
        if (!data.first_line_imaging && !data.alternatives && !data.usually_not_appropriate) {
            const instructionEl = document.createElement('p');
            instructionEl.className = 'acr-instruction';
            instructionEl.textContent = data.instructions || 'View the ACR website for detailed appropriateness ratings.';
            body.appendChild(instructionEl);
        }

        container.appendChild(body);
        return container;
    }

    createACRSection(title, items, type) {
        const section = document.createElement('div');
        section.className = `acr-section acr-${type}`;
        section.innerHTML = `
            <div class="acr-section-header">
                <span class="acr-badge ${type}">${type === 'appropriate' ? '7-9' : type === 'maybe' ? '4-6' : '1-3'}</span>
                <span class="acr-section-title">${title}</span>
            </div>
            <ul class="acr-list">
                ${items.map(item => `<li>${item}</li>`).join('')}
            </ul>
        `;
        return section;
    }

    formatMessage(text) {
        return marked.parse(text, { breaks: true, gfm: true });
    }

    parseAndRenderToolResults(bubbleEl, text) {
        // Remove tool call loader
        const loader = bubbleEl.querySelector('.tool-call-loader');
        if (loader) loader.remove();

        // Check for phone numbers and make them clickable
        // Matches: (919) 684-7213, 919-684-7213, 684-7213
        const phonePattern = /\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g;
        const phones = text.match(phonePattern);

        if (phones && phones.length > 0) {
            let enhanced = bubbleEl.innerHTML;
            enhanced = enhanced.replace(
                /\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g,
                match => {
                    const digits = match.replace(/\D/g, '');
                    return `<a href="tel:${digits}" class="inline-phone">${match}</a>`;
                }
            );
            bubbleEl.innerHTML = enhanced;
        }
    }

    renderContactResults(contacts, timeContext) {
        const container = document.createElement('div');
        container.className = 'data-card';

        const header = document.createElement('div');
        header.className = 'data-card-header';
        header.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
            </svg>
            <span>Directory</span>
        `;
        container.appendChild(header);

        const body = document.createElement('div');
        body.className = 'data-card-body';

        const grid = document.createElement('div');
        grid.className = 'contacts-grid';

        contacts.forEach(contact => {
            const card = this.createContactCard(contact);
            grid.appendChild(card);
        });

        body.appendChild(grid);
        container.appendChild(body);
        return container;
    }

    createContactCard(contact) {
        const card = document.createElement('div');
        card.className = `contact-card ${contact.available_now ? '' : 'unavailable'}`;

        const statusText = contact.available_now ? 'Available' : 'After hours';
        const typeMap = {
            'interpretation_questions': 'Reading Room',
            'scheduling_inpatient': 'Scheduling',
            'tech_scheduling': 'Tech',
            'scanner_direct': 'Scanner',
            'procedure_request': 'Procedure'
        };
        const typeBadge = typeMap[contact.study_status] || contact.study_status || '';
        const phoneDigits = (contact.phone || '').replace(/\D/g, '');

        card.innerHTML = `
            <div class="contact-header">
                <div class="contact-status">
                    <span class="availability-dot"></span>
                    <span class="availability-text">${statusText}</span>
                </div>
                ${typeBadge ? `<span class="contact-type-badge">${typeBadge}</span>` : ''}
            </div>
            <h4 class="contact-department">${contact.department || 'Unknown'}</h4>
            <a class="contact-phone" href="tel:${phoneDigits}">${contact.phone || 'N/A'}</a>
            ${contact.description ? `<p class="contact-description">${contact.description}</p>` : ''}
            <div class="contact-meta">
                ${contact.modalities && contact.modalities.length ? `<span>${contact.modalities.join(', ')}</span>` : ''}
                ${contact.location ? `<span>${contact.location}</span>` : ''}
            </div>
        `;

        return card;
    }

    renderACRResults(data) {
        const container = document.createElement('div');
        container.className = 'acr-results';

        if (data.title) {
            const header = document.createElement('div');
            header.className = 'acr-header';
            header.innerHTML = `
                <h3 class="acr-title">${data.title}</h3>
                ${data.synopsis ? `
                    <div class="acr-synopsis">
                        ${data.synopsis.map(s => `<span class="acr-synopsis-item">${s}</span>`).join('')}
                    </div>
                ` : ''}
            `;
            container.appendChild(header);
        }

        if (data.variants) {
            data.variants.forEach((variant, index) => {
                const variantEl = this.createVariantCard(variant, index + 1);
                container.appendChild(variantEl);
            });
        }

        return container;
    }

    createVariantCard(variant, number) {
        const card = document.createElement('div');
        card.className = 'acr-variant';

        const header = document.createElement('div');
        header.className = 'variant-header';
        header.innerHTML = `
            <span class="variant-number">${number}</span>
            <span class="variant-description">${variant.description || variant.clinical_scenario || `Variant ${number}`}</span>
        `;
        card.appendChild(header);

        const procedures = document.createElement('div');
        procedures.className = 'variant-procedures';

        if (variant.procedures) {
            variant.procedures.forEach(proc => {
                const procEl = this.createProcedureRow(proc);
                procedures.appendChild(procEl);
            });
        }

        card.appendChild(procedures);
        return card;
    }

    createProcedureRow(procedure) {
        const row = document.createElement('div');
        row.className = 'acr-procedure';

        const score = procedure.score || 0;
        let scoreClass = 'maybe';
        if (score >= 7) scoreClass = 'appropriate';
        else if (score <= 3) scoreClass = 'not-appropriate';

        const radiationLabel = {
            'none': 'No radiation',
            'low': 'Low dose',
            'medium': 'Medium dose',
            'high': 'High dose'
        };

        row.innerHTML = `
            <div class="procedure-score ${scoreClass}">
                <span class="score-value">${score || '?'}</span>
            </div>
            <div class="procedure-details">
                <span class="procedure-name">${procedure.name}</span>
                <div class="procedure-meta">
                    ${procedure.radiation_level ? `
                        <span class="radiation-badge ${procedure.radiation_level}">${radiationLabel[procedure.radiation_level] || procedure.radiation_level}</span>
                    ` : ''}
                    ${procedure.contrast?.contrast_detail ? `
                        <span class="contrast-badge">${procedure.contrast.contrast_detail}</span>
                    ` : ''}
                </div>
            </div>
        `;

        return row;
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    showToast(message, type = 'info') {
        // Remove existing toast if any
        const existing = document.querySelector('.toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);

        // Trigger animation
        requestAnimationFrame(() => toast.classList.add('show'));

        // Auto-dismiss (longer for errors)
        const duration = type === 'error' ? 6000 : 4000;
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.radChat = new RadChat();
});
