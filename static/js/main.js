document.addEventListener('DOMContentLoaded', function() {
    // Ensure jQuery is loaded
    if (typeof jQuery !== 'undefined') {
        // Initialize timezone selector with select2
        $(document).ready(function() {
            $('#timezone').select2({
                theme: 'bootstrap-5',
                width: '100%',
                placeholder: 'Search for a timezone...',
                allowClear: false
            });
        });
    } else {
        console.error("jQuery is not loaded properly");
    }
    
    // URL field validation
    const urlInput = document.getElementById('url');
    urlInput.addEventListener('invalid', function(e) {
        e.preventDefault();
        this.classList.add('is-invalid');
        this.placeholder = 'required field';
    });

    urlInput.addEventListener('input', function() {
        if (this.value) {
            this.classList.remove('is-invalid');
            this.placeholder = 'https://meetings.hubspot.com/your-name/30min';
        }
    });
    
    // Set tomorrow as default date
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];
    
    // Calculate max date (2 weeks from tomorrow)
    const maxDate = new Date(tomorrow);
    maxDate.setDate(maxDate.getDate() + 13); // 13 days after tomorrow = 2 weeks total
    const maxDateStr = maxDate.toISOString().split('T')[0];
    
    // Initialize date pickers
    const startDatePicker = flatpickr("#start_date", {
        dateFormat: "Y-m-d",
        minDate: "today",
        maxDate: maxDateStr,
        defaultDate: tomorrowStr,
        monthSelectorType: "static",
        showMonths: 1,
        static: true,
        disableYearOverlay: true,
        altFormat: "Y-m-d",
        todayBtn: true,
        onDayCreate: function(dObj, dStr, fp, dayElem) {
            // Add tooltip and class to disabled dates
            if (dayElem.classList.contains('flatpickr-disabled')) {
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                const currentDate = new Date(dObj);
                currentDate.setHours(0, 0, 0, 0);
                
                if (currentDate < today) {
                    dayElem.title = 'Date in the past';
                    dayElem.setAttribute('aria-label', 'past date');
                    dayElem.classList.add('disabled-past');
                } else {
                    dayElem.title = 'Date outside 2-week range';
                    dayElem.setAttribute('aria-label', 'future date');
                    dayElem.classList.add('disabled-future');
                }
            }
        },
        onChange: function(selectedDates, dateStr) {
            if (selectedDates[0]) {
                // Calculate max end date (2 weeks from start)
                const maxEndDate = new Date(selectedDates[0]);
                maxEndDate.setDate(maxEndDate.getDate() + 13); // 13 days after start = 2 weeks total

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
        minDate: tomorrowStr,
        maxDate: maxDateStr,
        defaultDate: tomorrowStr,
        monthSelectorType: "static",
        showMonths: 1,
        static: true,
        disableYearOverlay: true,
        altFormat: "Y-m-d",
        todayBtn: true,
        onDayCreate: function(dObj, dStr, fp, dayElem) {
            // Add tooltip and aria-label to disabled dates
            if (dayElem.classList.contains('flatpickr-disabled')) {
                const startDate = startDatePicker.selectedDates[0];
                if (startDate) {
                    const currentDate = new Date(dObj);
                    if (currentDate < startDate) {
                        dayElem.title = 'Date before start date';
                        dayElem.setAttribute('aria-label', 'before start date');
                        dayElem.classList.add('disabled-before');
                    } else {
                        dayElem.title = 'Date after 2-week range';
                        dayElem.setAttribute('aria-label', 'after 2-week range');
                        dayElem.classList.add('disabled-after');
                    }
                } else {
                    dayElem.title = 'Date outside 2-week range';
                }
            }
        },
        disable: [
            function(date) {
                if (!startDatePicker.selectedDates[0]) return true;
                const startDate = startDatePicker.selectedDates[0];
                const maxDate = new Date(startDate);
                maxDate.setDate(maxDate.getDate() + 13); // 13 days after start = 2 weeks total
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
        if (diffDays > 13) { // Changed from 14 to 13 to match the 2-week limit
            errorDiv.textContent = 'Please select a maximum of 2 consecutive weeks';
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

            // Display timezone info
            let infoText = [];
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

            // Format date
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

            // Join blocks with comma and show date
            return `${formattedDate}: ${timeBlocks.join(', ')}`;
        }).filter(Boolean).join('\n');
    }

    function formatTimeBlock(startTime, endTime, increment_minutes) {
        // Split times into components
        const [startTimeStr, startPeriod] = startTime.split(' ');
        const [endTimeStr, endPeriod] = endTime.split(' ');

        console.log('Time Block Components:', {
            startTimeStr,
            startPeriod,
            endTimeStr,
            endPeriod,
            increment_minutes
        });

        // Parse end time for increment calculation
        const [endHours, endMinutes] = endTimeStr.split(':').map(Number);

        // Convert to 24-hour format for calculation
        let hours24 = endHours;
        // Normalize period to uppercase for consistent comparison
        const normalizedPeriod = endPeriod.toUpperCase();
        
        if (normalizedPeriod === 'PM' && endHours !== 12) hours24 += 12;
        if (normalizedPeriod === 'AM' && endHours === 12) hours24 = 0;

        console.log('24-hour conversion:', {
            originalHours: endHours,
            period: endPeriod,
            normalizedPeriod: normalizedPeriod,
            convertedHours: hours24
        });

        // Create date and add increment
        const date = new Date(2000, 0, 1, hours24, endMinutes);
        date.setMinutes(date.getMinutes() + increment_minutes);

        // Convert back to 12-hour format
        let finalHours = date.getHours();
        const finalPeriod = finalHours >= 12 ? 'PM' : 'AM';
        finalHours = finalHours % 12 || 12;
        const finalMinutes = date.getMinutes().toString().padStart(2, '0');

        console.log('Final time calculation:', {
            finalHours,
            finalMinutes,
            finalPeriod
        });

        // Format the final string
        const formattedTime = `${startTimeStr}-${finalHours}:${finalMinutes} ${finalPeriod}`;
        console.log('Formatted output:', formattedTime);

        return formattedTime;
    }
});