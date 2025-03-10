document.addEventListener('DOMContentLoaded', function() {
    // Initialize date pickers
    const startDatePicker = flatpickr("#start_date", {
        dateFormat: "Y-m-d",
        minDate: "today",
        monthSelectorType: "static",
        showMonths: 1,
        static: true,
        onChange: function(selectedDates, dateStr) {
            if (selectedDates[0]) {
                // Calculate max end date (2 weeks from start)
                const maxEndDate = new Date(selectedDates[0]);
                maxEndDate.setDate(maxEndDate.getDate() + 14);

                // Update end date picker configuration
                endDatePicker.set('minDate', dateStr);
                endDatePicker.set('maxDate', maxEndDate);

                // If end date is outside the allowed range, update it
                if (endDatePicker.selectedDates[0]) {
                    if (endDatePicker.selectedDates[0] < selectedDates[0]) {
                        endDatePicker.setDate(dateStr);
                    } else if (endDatePicker.selectedDates[0] > maxEndDate) {
                        endDatePicker.setDate(maxEndDate);
                    }
                }
            }
        }
    });

    const endDatePicker = flatpickr("#end_date", {
        dateFormat: "Y-m-d",
        minDate: "today",
        monthSelectorType: "static",
        showMonths: 1,
        static: true,
        disable: [
            function(date) {
                if (!startDatePicker.selectedDates[0]) return true;
                const startDate = startDatePicker.selectedDates[0];
                const maxDate = new Date(startDate);
                maxDate.setDate(maxDate.getDate() + 14);
                return date < startDate || date > maxDate;
            }
        ]
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

        // Validate dates
        const startDate = new Date(form.start_date.value);
        const endDate = new Date(form.end_date.value);

        if (endDate < startDate) {
            errorDiv.textContent = 'End Date cannot be earlier than Start Date';
            errorDiv.classList.remove('d-none');
            return;
        }

        // Calculate date difference
        const diffTime = Math.abs(endDate - startDate);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        if (diffDays > 14) {
            errorDiv.textContent = 'Sorry: maximum 2 week span';
            errorDiv.classList.remove('d-none');
            return;
        }

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
        if (!availability) return '';

        return availability.map(slot => {
            if (!slot.times || slot.times.length === 0) return '';

            // Format date in shorter form
            const dateObj = new Date(slot.date.replace(/(\d+)(st|nd|rd|th)/, '$1'));
            const formattedDate = dateObj.toLocaleDateString('en-US', { 
                month: 'short', 
                day: 'numeric'
            });

            // Group consecutive times
            const timeBlocks = [];
            let currentBlock = {
                start: slot.times[0],
                end: slot.times[0]
            };

            for (let i = 1; i < slot.times.length; i++) {
                const currentTime = new Date(`2000/01/01 ${slot.times[i]}`);
                const prevTime = new Date(`2000/01/01 ${slot.times[i-1]}`);
                const diffMinutes = (currentTime - prevTime) / (1000 * 60);

                if (diffMinutes <= increment_minutes) {
                    currentBlock.end = slot.times[i];
                } else {
                    // Add current block
                    timeBlocks.push(formatTimeBlock(currentBlock.start, currentBlock.end, increment_minutes));
                    currentBlock = {
                        start: slot.times[i],
                        end: slot.times[i]
                    };
                }
            }

            // Add the last block
            timeBlocks.push(formatTimeBlock(currentBlock.start, currentBlock.end, increment_minutes));

            return `${formattedDate}: ${timeBlocks.join(', ')}`;
        }).filter(Boolean).join('\n');
    }

    function formatTimeBlock(startTime, endTime, increment_minutes) {
        // Extract components from start time
        const [startTimeOnly] = startTime.split(' ');

        // Calculate end time with increment
        const [endTimeOnly, endPeriod] = calculateEndTime(endTime, increment_minutes);

        // Format as "startTime-endTime period"
        return `${startTimeOnly}-${endTimeOnly} ${endPeriod}`;
    }

    function calculateEndTime(timeStr, increment) {
        const [time, period] = timeStr.split(' ');
        const [hours, minutes] = time.split(':').map(Number);

        // Convert to 24-hour format
        let hour24 = hours;
        if (period === 'PM' && hours !== 12) hour24 += 12;
        if (period === 'AM' && hours === 12) hour24 = 0;

        // Create date object and add increment
        const date = new Date(2000, 0, 1, hour24, minutes);
        date.setMinutes(date.getMinutes() + increment);

        // Convert back to 12-hour format
        let newHours = date.getHours();
        const newPeriod = newHours >= 12 ? 'PM' : 'AM';
        newHours = newHours % 12 || 12;

        return [`${newHours}:${date.getMinutes().toString().padStart(2, '0')}`, newPeriod];
    }
});