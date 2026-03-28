/**
 * Confetti burst animation — pure JS, no dependencies.
 */
function launchConfetti(count = 80) {
    const container = document.createElement('div');
    container.className = 'confetti-container';
    document.body.appendChild(container);

    const colors = ['#667eea', '#764ba2', '#f093fb', '#ffd700', '#ff6b6b', '#28a745', '#17a2b8', '#fff'];

    for (let i = 0; i < count; i++) {
        const piece = document.createElement('div');
        piece.className = 'confetti-piece';
        piece.style.left = Math.random() * 100 + '%';
        piece.style.background = colors[Math.floor(Math.random() * colors.length)];
        piece.style.width = (Math.random() * 8 + 5) + 'px';
        piece.style.height = (Math.random() * 8 + 5) + 'px';
        piece.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
        piece.style.animationDuration = (Math.random() * 2 + 2) + 's';
        piece.style.animationDelay = (Math.random() * 0.8) + 's';
        piece.style.opacity = Math.random() * 0.8 + 0.2;
        container.appendChild(piece);
    }

    setTimeout(() => container.remove(), 5000);
}
