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
        this.shiftIndicator = document.getElementById('shiftIndicator');
        this.welcomeState = document.getElementById('welcomeState');
        this.quickActions = document.getElementById('quickActions');

        this.selectedModel = { id: 'openai/gpt-4o-mini', name: 'GPT-4o Mini' };
        this.user = null;

        // Auth elements
        this.authArea = document.getElementById('authArea');
        this.loginBtn = document.getElementById('loginBtn');

        this.init();
    }

    generateSessionId() {
        return 'session_' + Math.random().toString(36).substring(2, 15);
    }

    async init() {
        this.bindEvents();
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

        // Close menu
        this.modelMenu.classList.remove('open');
        this.modelBtn.classList.remove('active');
    }

    async checkAuthStatus() {
        try {
            const response = await fetch('/auth/status');
            const data = await response.json();

            if (data.authenticated && data.user) {
                this.user = data.user;
                this.renderUserInfo();
            } else {
                this.user = null;
                this.renderLoginButton();
            }
        } catch (error) {
            console.error('Failed to check auth status:', error);
            this.renderLoginButton();
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
            heading.textContent = 'How can I help?';
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
        const bubbleEl = assistantMessage.querySelector('.message-bubble');

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
                                    this.addToolCallIndicator(bubbleEl, startMatch[1]);
                                    buffer = buffer.slice(startMatch.index + startMatch[0].length);
                                    continue;
                                }

                                // Check for tool result marker
                                const resultMatch = buffer.match(/__TOOL_RESULT__(.+?)__/);
                                if (resultMatch) {
                                    buffer = buffer.slice(resultMatch.index + resultMatch[0].length);
                                    try {
                                        const toolData = JSON.parse(resultMatch[1]);
                                        toolResults.push(toolData);
                                        this.renderToolResult(bubbleEl, toolData);
                                    } catch (e) {
                                        console.error('Failed to parse tool result:', e);
                                    }
                                    continue;
                                }

                                // No more markers, output remaining buffer as text
                                // But keep last 50 chars in case marker is split across chunks
                                if (buffer.length > 50 && !buffer.includes('__')) {
                                    fullText += buffer;
                                    bubbleEl.innerHTML = this.formatMessage(fullText);
                                    buffer = '';
                                }
                                break;
                            }
                        }
                    } catch (e) {
                        // Skip invalid JSON
                    }
                }
            }

            // Process any remaining buffer
            if (buffer) {
                fullText += buffer;
            }

            // Final render
            bubbleEl.innerHTML = this.formatMessage(fullText);
            this.parseAndRenderToolResults(bubbleEl, fullText);

            // Append any tool result cards that were rendered
            toolResults.forEach(tr => {
                const existingCard = bubbleEl.querySelector(`[data-tool="${tr.tool}"]`);
                if (!existingCard) {
                    this.renderToolResult(bubbleEl, tr);
                }
            });

            // Add model footer
            const modelName = assistantMessage.dataset.model;
            if (modelName) {
                this.addModelFooter(bubbleEl, modelName);
            }

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

    addMessage(role, content, isLoading = false) {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${role}`;

        const bubbleEl = document.createElement('div');
        bubbleEl.className = 'message-bubble';

        if (isLoading) {
            bubbleEl.innerHTML = `
                <div class="loading-dots">
                    <span></span><span></span><span></span>
                </div>
            `;
            // Store model name for later
            messageEl.dataset.model = this.selectedModel.name;
        } else {
            bubbleEl.innerHTML = this.formatMessage(content);
        }

        messageEl.appendChild(bubbleEl);
        this.chatMessages.appendChild(messageEl);
        this.scrollToBottom();

        return messageEl;
    }

    addModelFooter(bubbleEl, modelName) {
        const footer = document.createElement('div');
        footer.className = 'message-footer';
        footer.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 8V4H8"/>
                <rect width="16" height="12" x="4" y="8" rx="2"/>
                <path d="M2 14h2"/>
                <path d="M20 14h2"/>
                <path d="M15 13v2"/>
                <path d="M9 13v2"/>
            </svg>
            <span>${modelName}</span>
        `;
        bubbleEl.appendChild(footer);
    }

    addToolCallIndicator(bubbleEl, toolName) {
        const existingLoader = bubbleEl.querySelector('.tool-call-loader');
        if (existingLoader) existingLoader.remove();

        // Clear loading dots
        const loadingDots = bubbleEl.querySelector('.loading-dots');
        if (loadingDots) loadingDots.remove();

        // Format tool name for display
        const displayName = toolName.replace(/_/g, ' ').replace(/search |get /gi, '');

        const loader = document.createElement('div');
        loader.className = 'tool-call-loader';
        loader.innerHTML = `
            <div class="tool-call">
                <div class="tool-call-header loading">
                    <svg class="tool-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 6v6l4 2"/>
                    </svg>
                    <span>Searching ${displayName}...</span>
                </div>
            </div>
        `;
        bubbleEl.appendChild(loader);
        this.scrollToBottom();
    }

    renderToolResult(bubbleEl, toolData) {
        // Remove tool call loader
        const loader = bubbleEl.querySelector('.tool-call-loader');
        if (loader) loader.remove();

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
                bubbleEl.appendChild(card);
            }
        } else if (type === 'acr') {
            // Render ACR results
            if (data.topics && data.topics.length > 0) {
                // Search results - show list of topics
                const card = this.renderACRSearchResults(data.topics);
                card.dataset.tool = tool;
                bubbleEl.appendChild(card);
            } else if (data.topic) {
                // Single topic detail
                const card = this.renderACRResults(data.topic);
                card.dataset.tool = tool;
                bubbleEl.appendChild(card);
            }
        }

        this.scrollToBottom();
    }

    renderACRSearchResults(topics) {
        const container = document.createElement('div');
        container.className = 'data-card';

        const header = document.createElement('div');
        header.className = 'data-card-header';
        header.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 12l2 2 4-4"/>
                <circle cx="12" cy="12" r="10"/>
            </svg>
            <span>ACR Criteria</span>
        `;
        container.appendChild(header);

        const body = document.createElement('div');
        body.className = 'data-card-body';

        topics.slice(0, 5).forEach(topic => {
            const item = document.createElement('div');
            item.className = 'acr-search-item';
            item.innerHTML = `
                <h4>${topic.title || topic.name}</h4>
                ${topic.clinical_condition ? `<p>${topic.clinical_condition}</p>` : ''}
            `;
            body.appendChild(item);
        });

        container.appendChild(body);
        return container;
    }

    formatMessage(text) {
        // Basic markdown-like formatting
        let formatted = text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/`(.+?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');

        return formatted;
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

    showToast(message) {
        // Remove existing toast if any
        const existing = document.querySelector('.toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        document.body.appendChild(toast);

        // Trigger animation
        requestAnimationFrame(() => toast.classList.add('show'));

        // Auto-dismiss after 4 seconds
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.radChat = new RadChat();
});
