const convertSelectPlaceholder = "please select a file";
const darkModeStylesHref = "dark-styles.css";
let sessionID = "new";
let darkmode = false;
let files = null;
let formats = null; // Formats of uploaded files
let toFormatOptions = null; // Possible formats to convert to

document.getElementById("theme-toggle").addEventListener("click", function() {
    setDarkMode(!darkmode);
});

window.onload = async function() {
    // Set darkmode based on user preference or cookie
    darkmodeCookie = document.cookie.split(";").find(row => row.startsWith("darkmode="))?.split("=")[1] || null; // Extract cookie
    if (darkmodeCookie !== null) {
        darkmodeCookie = (darkmodeCookie === "true");
        setDarkMode(darkmodeCookie);
    } else {
        setDarkMode(window.matchMedia("(prefers-color-scheme: dark)").matches);
    }

    // Get supported formats
    let supportedFormats = [];
    try {
        let response = await fetch(
            `${window.env.BACKEND_URL}/supported-formats/`, 
            {method: "get"}
        );
        supportedFormats = await response.json();
    } catch (error) {
        handleError(error, "getting supported formats");
    }

    // Remove placeholder
    document.getElementById("supported-formats-placeholder").remove();

    // Get longest column (number of rows to add)
    let maxLength = 0;
    for (const mediaTypeFormats of Object.values(supportedFormats)) {
        if (mediaTypeFormats.length > maxLength) {
            maxLength = mediaTypeFormats.length;
        }
    }

    // Add rows to table
    for (let id =0; id < maxLength; ++id) {
        let tr = document.createElement("tr");
        tr.id = `tr${id}`;
        document.getElementById("supported-formats-table").appendChild(tr);
    }

    // Add formats to supported-formats table
    for (const mediaFormats of Object.values(supportedFormats)) {
        for (let index=0; index < mediaFormats.length; ++index) {
            let td = document.createElement("td");
            td.innerText = mediaFormats[index];
            document.getElementById(`tr${index}`).appendChild(td);
        }
    }
}

function setDarkMode(darkMode) {
    // Sets darkmode by toggling dark-styles.css stylesheet.
    if (darkMode) {
        darkmode = true;
        document.getElementById("dark-styles").href = darkModeStylesHref;
        document.getElementById("theme-icon-light").style.display = "block";
        document.getElementById("theme-icon-dark").style.display = "none";
    } else {
        darkmode = false;
        document.getElementById("dark-styles").href = "";
        document.getElementById("theme-icon-light").style.display = "none";
        document.getElementById("theme-icon-dark").style.display = "block";
    }
    document.cookie = `darkmode=${darkmode};`; // Set cookie
}

async function updateToFormats() {
    // Updates the options of the format-select element.

    function setOptions(value, clear) {
        // Adds option to the #format-select select. If clear is true, then the options will be cleared before adding value.
        if (clear) {
            document.getElementById("format-select").innerHTML = "";
        }
        let option = document.createElement("option");
        option.value = value;
        option.innerHTML = value;
        document.getElementById("format-select").appendChild(option);
    }
    document.getElementById("download-again").style.display = "none"; // Hide download again link
    
    let files = document.getElementById("file-input").files;
    // Check if no files have been selected.
    if (Array.from(files).length == 0) {
        setOptions(convertSelectPlaceholder, true);
        return;
    }

    // Get formats list
    formats = [];
    toFormatOptions = [];
    for (const file of Array.from(files)) {
        let format = file.name.split(".")[file.name.split(".").length - 1].toUpperCase();
        formats.push(format);
        try {
            let response = await fetch(
                `${window.env.BACKEND_URL}/supported-conversions/?format=${format}`, 
                {method: "get"}
            );
            let json = await response.json();
            if (response.ok) {
                toFormatOptions.push(json);
            } else {
                // Clear variables so that files can't be converted
                files = null;
                formats = null;
                toFormatOptions = null;
                setUserFeedback("Please select files with valid formats.", "orange");
                setOptions(convertSelectPlaceholder, true);
                return;
            }
        } catch (error) {
            // Clear variables so that files can't be converted
            files = null;
            formats = null;
            toFormatOptions = null;
            setOptions(convertSelectPlaceholder, true);
            handleError(error, "getting valid conversion options");
            return;
        }
    }

    // Filter for formats that all files can be converted to.
    let common = [];
    for (const options of toFormatOptions) {
        for (const format of options) {
            let isCommon = true;
            for (const options2 of toFormatOptions) {
                if (!options2.includes(format)) {
                isCommon = false;
                break; // No need to check other lists
                }
            }
            if (isCommon && !common.includes(format)) {
                common.push(format); // Add format to common if it is found in all lists and isn't already in common
            }
        }
    }
    toFormatOptions = common;

    // Set options
    if (toFormatOptions.length !== 0) {
        document.getElementById("format-select").innerHTML = "";
        for (const format of toFormatOptions) {
            setOptions(format, false);
        }
        setUserFeedback("", "black"); // Clear user feedback
    } else {
        // Clear variables so that files can't be converted
        files = null;
        formats = null;
        toFormatOptions = null;
        setUserFeedback("Please select files of the same media type.", "orange");
        setOptions(convertSelectPlaceholder, true);
    }
}

async function convertFile() {
    /* 
    Converts the file.
    Called by the submission of the #convert form.
    */
    document.getElementById("download-again").style.display = "none"; // Hide download again link

    let toFormat = document.getElementById("format-select").value;
    files = document.getElementById("file-input").files;

    // Check a file has been selected
    if (files == null || files.length == 0 || formats == null) {
        setUserFeedback("Please select a file to convert.", "orange");
        return;
    }
    // Check all files can be converted to a shared format
    if (toFormatOptions == null) {
        setUserFeedback("Please select files of the same media type.", "orange");
        return;
    }
    // Check toFormat is valid
    if (!toFormatOptions.includes(toFormat)) {
        setUserFeedback("Please select a valid format to convert to.", "orange");
        return;
    }

    // Check conversions with backend.
    for (const format of formats) {
        try {
            let response = await fetch(
                `${window.env.BACKEND_URL}/is-valid-conversion/?from_format=${format}&to_format=${toFormat}`, 
                {method: "get"}
            );
            json = await response.json();
            if (response.ok) {
                if (!json) {
                    setUserFeedback(`File format ${format} cannot be converted to ${toFormat}`, "orange");
                    return;
                }
            } else {
                handleError(json["detail"], "checking conversions");
            }
        } catch (error) {
            handleError(error, "checking conversions");
        }
    }

    document.getElementById("convert-loader").style.display = "block"; // Show loader

    // Upload file
    try {
        setUserFeedback("Uploading files...", "green");

        let formData = new FormData();
        for (const file of Array.from(files)) {
            formData.append("files", file); // Add file to body
        }

        let response = await fetch(
            `${window.env.BACKEND_URL}/upload/?session_id=${sessionID}`, 
            {method: "POST", 
            body: formData}
        );
        let json = await response.json();

        if (response.ok) {
            sessionID = json["session_id"];
            setUserFeedback(`Files uploaded successfully. Converting to ${toFormat}...`, "green");
        } else {
            handleError(json["detail"], "uploading file");
            return;
        }
    } catch (error) {
        handleError(error, "uploading file");
        return;
    }

    // Convert file
    try {
        let response = await fetch(
            `${window.env.BACKEND_URL}/convert/?session_id=${sessionID}&to_format=${toFormat}`, 
            {method: "PATCH"}
        );
        let json = await response.json();

        if (response.ok) {
            setUserFeedback(`Files successfully converted to ${toFormat}. Downloading files from server...`, "green");
        } else {
            handleError(json["detail"], "converting file");
            return;
        }
    } catch (error) {
        handleError(error, "converting file");
        return;
    }
    
    // Download file
    try {
        let response = await fetch(
            `${window.env.BACKEND_URL}/download/?session_id=${sessionID}`, 
            {method: "GET"}
        );
        if (response.ok) {
            let fileName = response.headers.get("filename");
            let blob = await response.blob();
            let link = window.URL.createObjectURL(blob);
            let a = document.createElement("a");
            a.href = link;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            document.getElementById("download-again-link").href = link;
            document.getElementById("download-again-link").download = fileName;
            document.getElementById("download-again").style.display = "inline";
            setUserFeedback("Files download started.", "green");
        } else {
            let json = await response.json();
            handleError(json["detail"], "downloading file");
            return;
        }
    } catch (error) {
        handleError(error, "downloading file");
        return;
    }
    sessionID = "new";
    document.getElementById("convert-loader").style.display = "none"; // Hide loader
    return;
}

function handleError(error, context) {
    // Handles errors and gives user feedback.
    let errorMessage;
    if (error instanceof Error) {
        errorMessage = error.message || JSON.stringify(error);
    } else {
        errorMessage = error;
    }
    setUserFeedback(`An error occured while ${context}. Please try again.`, "red");
    console.error(`An error occured while ${context}. Error: ${errorMessage}`);
    document.getElementById("convert-loader").style.display = "none"; // Hide loader
}

function setUserFeedback(text, color) {
    /* 
    Sets the innerText and style.color properties of the element #user-feedback
    If color is red or orange, then #user-feedback will be bold.
     */
    document.getElementById("user-feedback").innerText = text;
    document.getElementById("user-feedback").style.color = color;
    if (color == "red" || color == "orange") {
        document.getElementById("user-feedback").style.fontWeight = "bold";
    } else {
        document.getElementById("user-feedback").style.fontWeight = "normal";
    }
}
