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
        this.shiftIndicator = document.getElementById('shiftIndicator');
        this.welcomeState = document.getElementById('welcomeState');
        this.quickActions = document.getElementById('quickActions');

        this.init();
    }

    generateSessionId() {
        return 'session_' + Math.random().toString(36).substring(2, 15);
    }

    async init() {
        this.bindEvents();
        await this.loadModels();
        this.updateShiftIndicator();
        setInterval(() => this.updateShiftIndicator(), 60000);
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
    }

    async loadModels() {
        try {
            const response = await fetch('/models');
            const data = await response.json();

            this.modelSelect.innerHTML = '';
            data.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.name;
                this.modelSelect.appendChild(option);
            });
        } catch (error) {
            console.error('Failed to load models:', error);
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
            let inToolCall = false;

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
                            const text = parsed.text;

                            // Detect tool call markers
                            if (text.includes('[Searching:')) {
                                inToolCall = true;
                                const toolName = text.match(/\[Searching: (.+?)\.{3}\]/)?.[1] || 'tools';
                                this.addToolCallIndicator(bubbleEl, toolName);
                            } else if (inToolCall && text.includes(']')) {
                                inToolCall = false;
                            } else {
                                fullText += text;
                                bubbleEl.innerHTML = this.formatMessage(fullText);
                            }
                        }
                    } catch (e) {
                        // Skip invalid JSON
                    }
                }
            }

            // Parse and render any tool results in the final text
            bubbleEl.innerHTML = this.formatMessage(fullText);
            this.parseAndRenderToolResults(bubbleEl, fullText);

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
        } else {
            bubbleEl.innerHTML = this.formatMessage(content);
        }

        messageEl.appendChild(bubbleEl);
        this.chatMessages.appendChild(messageEl);
        this.scrollToBottom();

        return messageEl;
    }

    addToolCallIndicator(bubbleEl, toolName) {
        const existingLoader = bubbleEl.querySelector('.tool-call-loader');
        if (existingLoader) existingLoader.remove();

        // Clear loading dots
        const loadingDots = bubbleEl.querySelector('.loading-dots');
        if (loadingDots) loadingDots.remove();

        const loader = document.createElement('div');
        loader.className = 'tool-call-loader';
        loader.innerHTML = `
            <div class="tool-call">
                <div class="tool-call-header loading">
                    <svg class="tool-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 6v6l4 2"/>
                    </svg>
                    <span>Searching ${toolName}...</span>
                </div>
            </div>
        `;
        bubbleEl.appendChild(loader);
        this.scrollToBottom();
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

        // Check for contact information patterns and render cards
        const phonePattern = /(\d{3}-\d{4})/g;
        const phones = text.match(phonePattern);

        if (phones && phones.length > 0) {
            // Enhance phone numbers to be clickable
            let enhanced = bubbleEl.innerHTML;
            enhanced = enhanced.replace(/(\d{3}-\d{4})/g, '<a href="tel:$1" class="inline-phone">$1</a>');
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

        card.innerHTML = `
            <div class="contact-header">
                <div class="contact-status">
                    <span class="availability-dot"></span>
                    <span class="availability-text">${statusText}</span>
                </div>
                ${typeBadge ? `<span class="contact-type-badge">${typeBadge}</span>` : ''}
            </div>
            <h4 class="contact-department">${contact.department}</h4>
            <a class="contact-phone" href="tel:${contact.phone}">${contact.phone}</a>
            <p class="contact-description">${contact.description || ''}</p>
            <div class="contact-meta">
                ${contact.modalities ? `<span>${contact.modalities.join(', ')}</span>` : ''}
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
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.radChat = new RadChat();
});
