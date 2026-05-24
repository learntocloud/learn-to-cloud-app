/**
 * Shared Alpine components for the curriculum UI.
 *
 * Defines two components:
 *
 * - ``copyButton`` — a button that copies a target string to the clipboard
 *   and flips the ``copied`` state to true for 2s. Used by the
 *   ``macros/code_block.html`` ``copy_code`` macro.
 *
 * - ``proseCopyButtons`` — an ``x-init`` directive style that walks all
 *   ``<pre>`` blocks within its element and appends a clipboard button.
 *   Used by the prose container that renders the markdown
 *   ``description_html`` so authored code fences get copy buttons too.
 */
document.addEventListener('alpine:init', () => {
    const copyText = (text) => {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text);
        }
        // Fallback for non-secure contexts and older browsers
        return new Promise((resolve) => {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            resolve();
        });
    };

    Alpine.data('copyButton', () => ({
        copied: false,
        copy(text) {
            copyText(text).then(() => {
                this.copied = true;
                setTimeout(() => { this.copied = false; }, 2000);
            });
        },
    }));

    Alpine.data('proseCopyButtons', () => ({
        init() {
            this.$el.querySelectorAll('pre').forEach((pre) => {
                if (pre.querySelector('.copy-btn')) return;
                pre.style.position = 'relative';
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'copy-btn absolute top-2 right-2 p-1 rounded-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-300';
                btn.setAttribute('aria-label', 'Copy code to clipboard');
                btn.innerHTML = '📋';
                btn.addEventListener('click', () => {
                    const code = pre.querySelector('code');
                    const text = code ? code.textContent : pre.textContent;
                    copyText(text).then(() => {
                        btn.innerHTML = '✓';
                        btn.classList.add('text-green-500');
                        setTimeout(() => {
                            btn.innerHTML = '📋';
                            btn.classList.remove('text-green-500');
                        }, 2000);
                    });
                });
                pre.appendChild(btn);
            });
        },
    }));
});
