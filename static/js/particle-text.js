/**
 * Particle Text Effect — ported from 21st.dev React component by kainxu
 * Vanilla JS canvas implementation
 */

class Particle {
    constructor() {
        this.pos = { x: 0, y: 0 };
        this.vel = { x: 0, y: 0 };
        this.acc = { x: 0, y: 0 };
        this.target = { x: 0, y: 0 };

        this.closeEnoughTarget = 100;
        this.maxSpeed = 1.0;
        this.maxForce = 0.1;
        this.particleSize = 10;
        this.isKilled = false;

        this.startColor = { r: 0, g: 0, b: 0 };
        this.targetColor = { r: 0, g: 0, b: 0 };
        this.colorWeight = 0;
        this.colorBlendRate = 0.01;
    }

    move() {
        let proximityMult = 1;
        const dx = this.pos.x - this.target.x;
        const dy = this.pos.y - this.target.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < this.closeEnoughTarget) {
            proximityMult = distance / this.closeEnoughTarget;
        }

        const toTarget = { x: this.target.x - this.pos.x, y: this.target.y - this.pos.y };
        const mag = Math.sqrt(toTarget.x * toTarget.x + toTarget.y * toTarget.y);
        if (mag > 0) {
            toTarget.x = (toTarget.x / mag) * this.maxSpeed * proximityMult;
            toTarget.y = (toTarget.y / mag) * this.maxSpeed * proximityMult;
        }

        const steer = { x: toTarget.x - this.vel.x, y: toTarget.y - this.vel.y };
        const sMag = Math.sqrt(steer.x * steer.x + steer.y * steer.y);
        if (sMag > 0) {
            steer.x = (steer.x / sMag) * this.maxForce;
            steer.y = (steer.y / sMag) * this.maxForce;
        }

        this.acc.x += steer.x;
        this.acc.y += steer.y;
        this.vel.x += this.acc.x;
        this.vel.y += this.acc.y;
        this.pos.x += this.vel.x;
        this.pos.y += this.vel.y;
        this.acc.x = 0;
        this.acc.y = 0;
    }

    draw(ctx, asPoints) {
        if (this.colorWeight < 1.0) {
            this.colorWeight = Math.min(this.colorWeight + this.colorBlendRate, 1.0);
        }

        const r = Math.round(this.startColor.r + (this.targetColor.r - this.startColor.r) * this.colorWeight);
        const g = Math.round(this.startColor.g + (this.targetColor.g - this.startColor.g) * this.colorWeight);
        const b = Math.round(this.startColor.b + (this.targetColor.b - this.startColor.b) * this.colorWeight);

        ctx.fillStyle = `rgb(${r},${g},${b})`;
        if (asPoints) {
            ctx.fillRect(this.pos.x, this.pos.y, 2, 2);
        } else {
            ctx.beginPath();
            ctx.arc(this.pos.x, this.pos.y, this.particleSize / 2, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    kill(w, h) {
        if (!this.isKilled) {
            const rp = randomPos(w / 2, h / 2, (w + h) / 2);
            this.target.x = rp.x;
            this.target.y = rp.y;

            this.startColor = {
                r: this.startColor.r + (this.targetColor.r - this.startColor.r) * this.colorWeight,
                g: this.startColor.g + (this.targetColor.g - this.startColor.g) * this.colorWeight,
                b: this.startColor.b + (this.targetColor.b - this.startColor.b) * this.colorWeight,
            };
            this.targetColor = { r: 0, g: 0, b: 0 };
            this.colorWeight = 0;
            this.isKilled = true;
        }
    }
}

function randomPos(x, y, mag) {
    const rx = Math.random() * 1000;
    const ry = Math.random() * 500;
    const dir = { x: rx - x, y: ry - y };
    const m = Math.sqrt(dir.x * dir.x + dir.y * dir.y);
    if (m > 0) {
        dir.x = (dir.x / m) * mag;
        dir.y = (dir.y / m) * mag;
    }
    return { x: x + dir.x, y: y + dir.y };
}

/**
 * Initialize particle text effect on a canvas element.
 * @param {HTMLCanvasElement} canvas
 * @param {Object} options
 * @param {string[]} options.words - Array of words to cycle through
 * @param {number} [options.pixelSteps=6] - Sampling density (lower = more particles)
 * @param {boolean} [options.drawAsPoints=true]
 * @param {number} [options.cycleFrames=240] - Frames between word changes (~4s at 60fps)
 * @param {string} [options.fontStyle] - CSS font string
 * @param {number} [options.canvasWidth=1000]
 * @param {number} [options.canvasHeight=500]
 * @param {{r,g,b}[]} [options.colors] - Color palette; random if omitted
 */
function initParticleText(canvas, options = {}) {
    const {
        words = ['HELLO', 'WORLD'],
        pixelSteps = 6,
        drawAsPoints = true,
        cycleFrames = 240,
        fontStyle = null,
        canvasWidth = 1000,
        canvasHeight = 500,
        colors = null,
    } = options;

    canvas.width = canvasWidth;
    canvas.height = canvasHeight;
    const ctx = canvas.getContext('2d');

    const particles = [];
    let frameCount = 0;
    let wordIndex = 0;
    let animId = null;
    let colorIndex = 0;

    const mouse = { x: 0, y: 0, pressed: false, right: false };

    function getNextColor() {
        if (colors && colors.length) {
            const c = colors[colorIndex % colors.length];
            colorIndex++;
            return c;
        }
        return { r: Math.random() * 255, g: Math.random() * 255, b: Math.random() * 255 };
    }

    function loadWord(word) {
        const off = document.createElement('canvas');
        off.width = canvasWidth;
        off.height = canvasHeight;
        const offCtx = off.getContext('2d');

        offCtx.fillStyle = 'white';
        offCtx.font = fontStyle || `bold ${Math.min(100, canvasWidth / (word.length * 0.7))}px Arial`;
        offCtx.textAlign = 'center';
        offCtx.textBaseline = 'middle';
        offCtx.fillText(word, canvasWidth / 2, canvasHeight / 2);

        const imgData = offCtx.getImageData(0, 0, canvasWidth, canvasHeight).data;
        const newColor = getNextColor();

        const coords = [];
        for (let i = 0; i < imgData.length; i += pixelSteps * 4) {
            coords.push(i);
        }
        // Shuffle for fluid motion
        for (let i = coords.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [coords[i], coords[j]] = [coords[j], coords[i]];
        }

        let pi = 0;
        for (const ci of coords) {
            if (imgData[ci + 3] > 0) {
                const x = (ci / 4) % canvasWidth;
                const y = Math.floor(ci / 4 / canvasWidth);

                let p;
                if (pi < particles.length) {
                    p = particles[pi];
                    p.isKilled = false;
                } else {
                    p = new Particle();
                    const rp = randomPos(canvasWidth / 2, canvasHeight / 2, (canvasWidth + canvasHeight) / 2);
                    p.pos.x = rp.x;
                    p.pos.y = rp.y;
                    p.maxSpeed = Math.random() * 6 + 4;
                    p.maxForce = p.maxSpeed * 0.05;
                    p.particleSize = Math.random() * 6 + 6;
                    p.colorBlendRate = Math.random() * 0.0275 + 0.0025;
                    particles.push(p);
                }

                p.startColor = {
                    r: p.startColor.r + (p.targetColor.r - p.startColor.r) * p.colorWeight,
                    g: p.startColor.g + (p.targetColor.g - p.startColor.g) * p.colorWeight,
                    b: p.startColor.b + (p.targetColor.b - p.startColor.b) * p.colorWeight,
                };
                p.targetColor = newColor;
                p.colorWeight = 0;
                p.target.x = x;
                p.target.y = y;

                pi++;
            }
        }

        for (let i = pi; i < particles.length; i++) {
            particles[i].kill(canvasWidth, canvasHeight);
        }
    }

    function animate() {
        // Motion blur background
        ctx.fillStyle = 'rgba(0, 0, 0, 0.1)';
        ctx.fillRect(0, 0, canvasWidth, canvasHeight);

        for (let i = particles.length - 1; i >= 0; i--) {
            const p = particles[i];
            p.move();
            p.draw(ctx, drawAsPoints);

            if (p.isKilled) {
                if (p.pos.x < -50 || p.pos.x > canvasWidth + 50 || p.pos.y < -50 || p.pos.y > canvasHeight + 50) {
                    particles.splice(i, 1);
                }
            }
        }

        // Mouse interaction
        if (mouse.pressed && mouse.right) {
            for (const p of particles) {
                const dx = p.pos.x - mouse.x;
                const dy = p.pos.y - mouse.y;
                if (Math.sqrt(dx * dx + dy * dy) < 50) {
                    p.kill(canvasWidth, canvasHeight);
                }
            }
        }

        frameCount++;
        if (frameCount % cycleFrames === 0) {
            wordIndex = (wordIndex + 1) % words.length;
            loadWord(words[wordIndex]);
        }

        animId = requestAnimationFrame(animate);
    }

    // Events
    canvas.addEventListener('mousedown', (e) => {
        mouse.pressed = true;
        mouse.right = e.button === 2;
        const r = canvas.getBoundingClientRect();
        mouse.x = (e.clientX - r.left) * (canvasWidth / r.width);
        mouse.y = (e.clientY - r.top) * (canvasHeight / r.height);
    });
    canvas.addEventListener('mouseup', () => { mouse.pressed = false; mouse.right = false; });
    canvas.addEventListener('mousemove', (e) => {
        const r = canvas.getBoundingClientRect();
        mouse.x = (e.clientX - r.left) * (canvasWidth / r.width);
        mouse.y = (e.clientY - r.top) * (canvasHeight / r.height);
    });
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());

    // Start
    loadWord(words[0]);
    animate();

    // Return destroy function
    return function destroy() {
        if (animId) cancelAnimationFrame(animId);
    };
}
