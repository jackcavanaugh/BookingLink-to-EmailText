document.addEventListener('DOMContentLoaded', function() {
    // Initialize date pickers
    flatpickr(".datepicker", {
        dateFormat: "Y-m-d",
        minDate: "today"
    });

    const form = document.getElementById('scraperForm');
    const submitBtn = document.getElementById('submitBtn');
    const spinner = submitBtn.querySelector('.spinner-border');
    const resultDiv = document.getElementById('result');
    const errorDiv = document.getElementById('error');
    const availabilityText = document.getElementById('availabilityText');
    const timezoneInfo = document.getElementById('timezoneInfo');
    const copyBtn = document.getElementById('copyBtn');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        // Reset UI states
        resultDiv.classList.add('d-none');
        errorDiv.classList.add('d-none');
        timezoneInfo.textContent = '';
        spinner.classList.remove('d-none');
        submitBtn.disabled = true;

        const formData = new FormData(form);

        try {
            const response = await fetch('/scrape', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to fetch availability');
            }

            // Display timezone info if available
            if (data.availability && data.availability[0]?.timezone) {
                timezoneInfo.textContent = `Times shown in ${data.availability[0].timezone}`;
            } else if (data.note) {
                timezoneInfo.textContent = data.note;
            }

            // Display results
            availabilityText.textContent = formatAvailability(data.availability);
            resultDiv.classList.remove('d-none');
        } catch (error) {
            errorDiv.textContent = error.message;
            errorDiv.classList.remove('d-none');
        } finally {
            spinner.classList.add('d-none');
            submitBtn.disabled = false;
        }
    });

    copyBtn.addEventListener('click', function() {
        navigator.clipboard.writeText(availabilityText.textContent)
            .then(() => {
                copyBtn.textContent = 'Copied!';
                setTimeout(() => {
                    copyBtn.innerHTML = '<i class="bi bi-clipboard"></i> Copy';
                }, 2000);
            });
    });

    function formatAvailability(availability) {
        return availability.map(slot => {
            let text = `[${slot.date}] ${slot.times.join(', ')}`;
            return text;
        }).join('\n');
    }
});