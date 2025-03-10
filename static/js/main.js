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
                // If no start date is selected, disable all dates
                if (!startDatePicker.selectedDates[0]) return true;

                const startDate = startDatePicker.selectedDates[0];
                const maxDate = new Date(startDate);
                maxDate.setDate(maxDate.getDate() + 14);

                // Disable if date is before start date or more than 2 weeks after
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

            // Group consecutive times into blocks
            const timeBlocks = [];
            let currentBlock = {
                start: slot.times[0],
                end: slot.times[0]
            };

            // Helper function to parse time and add minutes
            function addMinutes(timeStr, minutes) {
                const [time, period] = timeStr.split(' ');
                const [hours, mins] = time.split(':').map(Number);
                const date = new Date(2000, 0, 1, 
                    period === 'PM' && hours !== 12 ? hours + 12 : hours === 12 && period === 'AM' ? 0 : hours, 
                    mins);
                date.setMinutes(date.getMinutes() + minutes);

                let newHours = date.getHours();
                const newMins = date.getMinutes();
                const newPeriod = newHours >= 12 ? 'PM' : 'AM';
                newHours = newHours % 12 || 12;

                return `${newHours}:${newMins.toString().padStart(2, '0')} ${newPeriod}`;
            }

            // Process consecutive times
            for (let i = 1; i < slot.times.length; i++) {
                const currentTime = new Date(`2000/01/01 ${slot.times[i]}`);
                const prevTime = new Date(`2000/01/01 ${slot.times[i-1]}`);
                const diffMinutes = (currentTime - prevTime) / (1000 * 60);

                if (diffMinutes <= increment_minutes) {
                    currentBlock.end = slot.times[i];
                } else {
                    // Get the final end time with period
                    const endTime = addMinutes(currentBlock.end, increment_minutes);
                    const [startTime] = currentBlock.start.split(' '); // Remove AM/PM from start
                    const [endTimeValue, endPeriod] = endTime.split(' '); // Keep AM/PM from end
                    timeBlocks.push(`${startTime}-${endTimeValue} ${endPeriod}`);

                    currentBlock = {
                        start: slot.times[i],
                        end: slot.times[i]
                    };
                }
            }

            // Add the last block
            const finalEndTime = addMinutes(currentBlock.end, increment_minutes);
            const [startTime] = currentBlock.start.split(' '); // Remove AM/PM from start
            const [endTimeValue, endPeriod] = finalEndTime.split(' '); // Keep AM/PM from end
            timeBlocks.push(`${startTime}-${endTimeValue} ${endPeriod}`);

            // Return formatted date with time blocks
            return `${formattedDate}: ${timeBlocks.join(', ')}`;
        }).filter(Boolean).join('\n');
    }
});