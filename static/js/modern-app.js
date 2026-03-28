const multiSelections = {};
let currentStep = 1;

function goToStep(step) {
    document.querySelectorAll('.step-screen').forEach(s => s.classList.remove('active'));
    const target = document.getElementById('step-' + step);
    if (target) {
        target.classList.add('active');
        currentStep = step;
        updateProgress();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

function nextStep() {
    if (validateStep(currentStep)) {
        goToStep(currentStep + 1);
    }
}

function prevStep() {
    if (currentStep > 1) {
        goToStep(currentStep - 1);
    }
}

function updateProgress() {
    var total = (typeof TOTAL_STEPS !== 'undefined') ? TOTAL_STEPS : 9;
    var progress = ((currentStep - 1) / total) * 100;
    var bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = progress + '%';
    var indicator = document.getElementById('step-indicator');
    if (indicator && currentStep > 1 && currentStep <= total) {
        indicator.textContent = 'Step ' + (currentStep - 1) + ' of ' + total;
        indicator.style.display = 'block';
    } else if (indicator) {
        indicator.style.display = 'none';
    }
}

function validateStep(step) {
    if (step === 1) return true;
    var total = (typeof TOTAL_STEPS !== 'undefined') ? TOTAL_STEPS : 9;
    if (step > total) return true;

    // Clear previous errors
    document.querySelectorAll('#step-' + step + ' .modern-input.error').forEach(function(el) { el.classList.remove('error'); });
    document.querySelectorAll('#step-' + step + ' .error-message').forEach(function(el) { el.classList.remove('visible'); });

    var valid = true;
    var sectionIndex = step - 2;
    if (typeof FORM_SECTIONS !== 'undefined' && FORM_SECTIONS[sectionIndex]) {
        var section = FORM_SECTIONS[sectionIndex];
        section.questions.forEach(function(q) {
            if (q.is_required) {
                if (q.field_type === 'multiselect') {
                    var sel = multiSelections[q.field_key];
                    if (!sel || sel.size === 0) {
                        var group = document.querySelector('[data-field="' + q.field_key + '"]');
                        if (group) showFieldError(group, q.label + ' is required');
                        valid = false;
                    }
                } else {
                    var el = document.querySelector('[data-field="' + q.field_key + '"]');
                    if (el && !el.value.trim()) {
                        markError(el, q.label + ' is required');
                        valid = false;
                    }
                }
            }
            if (q.field_type === 'email') {
                var el = document.querySelector('[data-field="' + q.field_key + '"]');
                if (el && el.value.trim() && !isValidEmail(el.value)) {
                    markError(el, 'Please enter a valid email address');
                    valid = false;
                }
            }
        });
    }
    return valid;
}

function markError(el, message) {
    el.classList.add('error');
    var errMsg = el.parentElement.querySelector('.error-message');
    if (!errMsg) {
        errMsg = document.createElement('div');
        errMsg.className = 'error-message';
        el.parentElement.appendChild(errMsg);
    }
    errMsg.textContent = message;
    errMsg.classList.add('visible');
}

function showFieldError(el, message) {
    var errMsg = el.parentElement.querySelector('.error-message');
    if (!errMsg) {
        errMsg = document.createElement('div');
        errMsg.className = 'error-message';
        el.parentElement.appendChild(errMsg);
    }
    errMsg.textContent = message;
    errMsg.classList.add('visible');
}

function isValidEmail(email) {
    return /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email);
}

function toggleChip(chip, fieldKey, value) {
    if (!multiSelections[fieldKey]) {
        multiSelections[fieldKey] = new Set();
    }
    if (multiSelections[fieldKey].has(value)) {
        multiSelections[fieldKey].delete(value);
        chip.classList.remove('selected');
    } else {
        multiSelections[fieldKey].add(value);
        chip.classList.add('selected');
    }
}

function collectFormData() {
    var data = {};
    document.querySelectorAll('[data-field]').forEach(function(el) {
        var key = el.dataset.field;
        if (el.dataset.type === 'multiselect') return;
        if (el.type === 'checkbox') {
            data[key] = el.checked;
        } else {
            data[key] = el.value.trim();
        }
    });
    for (var key in multiSelections) {
        data[key] = Array.from(multiSelections[key]);
    }
    return data;
}

function getBaseUrl() {
    return (typeof AGENCY_SLUG !== 'undefined' && AGENCY_SLUG) ? '/a/' + AGENCY_SLUG : '';
}

async function submitForm() {
    var data = collectFormData();
    var overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.remove('hidden');

    try {
        var response = await fetch(getBaseUrl() + '/onboard', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        var result = await response.json();
        if (overlay) overlay.classList.add('hidden');

        if (result.success) {
            var idDisplay = document.getElementById('onboarding-id-display');
            if (idDisplay) idDisplay.textContent = result.onboarding_id;
            var dashLink = document.getElementById('dashboard-link');
            if (dashLink) dashLink.href = result.dashboard_url;
            showCredentials(data.email, result.client_password);
            var total = (typeof TOTAL_STEPS !== 'undefined') ? TOTAL_STEPS : 9;
            goToStep(total + 1);
            if (typeof launchConfetti === 'function') launchConfetti(100);
        } else {
            alert('Error: ' + (result.errors || []).join('\n'));
        }
    } catch (err) {
        if (overlay) overlay.classList.add('hidden');
        alert('An error occurred. Please try again.');
        console.error(err);
    }
}

function showCredentials(email, password) {
    var box = document.getElementById('credentials-box');
    var credEmail = document.getElementById('cred-email');
    var credPassword = document.getElementById('cred-password');
    if (box && credEmail && credPassword && password) {
        credEmail.textContent = email;
        credPassword.textContent = password;
        box.style.display = 'block';
    }
}

async function submitDemo() {
    var overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.remove('hidden');

    try {
        var response = await fetch(getBaseUrl() + '/demo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        var result = await response.json();
        if (overlay) overlay.classList.add('hidden');

        if (result.success) {
            var idDisplay = document.getElementById('onboarding-id-display');
            if (idDisplay) idDisplay.textContent = result.onboarding_id;
            var dashLink = document.getElementById('dashboard-link');
            if (dashLink) dashLink.href = result.dashboard_url;
            showCredentials('hello@acmecorp.com', result.client_password);
            var total = (typeof TOTAL_STEPS !== 'undefined') ? TOTAL_STEPS : 9;
            goToStep(total + 1);
            if (typeof launchConfetti === 'function') launchConfetti(100);
        } else {
            alert('Error: ' + (result.errors || []).join('\n'));
        }
    } catch (err) {
        if (overlay) overlay.classList.add('hidden');
        alert('An error occurred. Please try again.');
        console.error(err);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    goToStep(1);
});
