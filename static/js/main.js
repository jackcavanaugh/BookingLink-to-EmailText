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

            // Display timezone and increment info
            let infoText = [];
            if (data.increment_minutes) {
                infoText.push(`Appointment length: ${data.increment_minutes} minutes`);
            }
            if (data.availability && data.availability[0]?.timezone) {
                infoText.push(`Times shown in ${data.availability[0].timezone}`);
            } else if (data.note) {
                infoText.push(data.note);
            }
            timezoneInfo.textContent = infoText.join(' • ');

            // Display results
            availabilityText.textContent = formatAvailability(data.availability, data.increment_minutes);
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

    function formatAvailability(availability, increment_minutes) {
        if (!availability || !increment_minutes) return '';

        return availability.map(slot => {
            if (!slot.times || slot.times.length === 0) return '';

            // Convert times to Date objects for comparison
            const timeObjects = slot.times.map(time => {
                const [hourMin, period] = time.split(' ');
                const [hours, minutes] = hourMin.split(':');
                const date = new Date();
                let hour = parseInt(hours);
                if (period.toLowerCase() === 'pm' && hour !== 12) hour += 12;
                if (period.toLowerCase() === 'am' && hour === 12) hour = 0;
                date.setHours(hour, parseInt(minutes), 0, 0);
                return date;
            }).sort((a, b) => a - b);

            // Group times into blocks
            const blocks = [];
            let currentBlock = [timeObjects[0]];

            for (let i = 1; i < timeObjects.length; i++) {
                const expectedNext = new Date(currentBlock[currentBlock.length - 1].getTime() + increment_minutes * 60000);
                if (timeObjects[i].getTime() === expectedNext.getTime()) {
                    currentBlock.push(timeObjects[i]);
                } else {
                    blocks.push(currentBlock);
                    currentBlock = [timeObjects[i]];
                }
            }
            blocks.push(currentBlock);

            // Format each block as a range
            const formatTime = (date) => {
                let hours = date.getHours();
                const minutes = date.getMinutes();
                const period = hours >= 12 ? 'PM' : 'AM';
                if (hours > 12) hours -= 12;
                if (hours === 0) hours = 12;
                return `${hours}:${minutes.toString().padStart(2, '0')}`;
            };

            const timeRanges = blocks.map(block => {
                const start = formatTime(block[0]);
                // Calculate end time by adding increment to the last time in block
                const endTime = new Date(block[block.length - 1].getTime() + increment_minutes * 60000);
                const end = formatTime(endTime);
                const period = endTime.getHours() >= 12 ? 'PM' : 'AM';
                return `${start}-${end} ${period}`;
            });

            return `[${slot.date}] ${timeRanges.join(', ')}`;
        }).filter(Boolean).join('\n');
    }
});