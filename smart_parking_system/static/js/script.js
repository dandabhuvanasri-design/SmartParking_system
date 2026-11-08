
/* =====================================
   SMART PARKING SYSTEM - JAVASCRIPT
===================================== */

document.addEventListener("DOMContentLoaded", function () {

    // Automatically hide flash messages after 5 seconds
    const flashMessages = document.querySelectorAll(".flash");

    flashMessages.forEach(function (message) {
        setTimeout(function () {
            message.style.transition = "opacity 0.5s ease";
            message.style.opacity = "0";

            setTimeout(function () {
                message.remove();
            }, 500);

        }, 5000);
    });


    // Prevent accidental multiple form submissions
    const forms = document.querySelectorAll("form");

    forms.forEach(function (form) {
        form.addEventListener("submit", function () {

            if (!form.checkValidity()) {
                return;
            }

            const submitButton = form.querySelector(
                'button[type="submit"]'
            );

            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = "Processing...";
            }

        });
    });

});
