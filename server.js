// server.js
require('dotenv').config();
const express = require('express');
const fs = require('fs').promises; // Use promises version of fs
const path = require('path');
const os = require('os'); // To display network IP address
// Import the automation function from the other file
// Adjust path if your file structure is different from fda-automation-backend/automation/fdaAutomator.js
const { automateFdaForm } = require('./automation/fdaAutomator'); // Make sure this path is correct

const app = express();

// Middleware to parse incoming JSON requests
app.use(express.json({ limit: '5mb' })); // Increased limit for potentially large payloads

const REPORTS_STORAGE_DIR = path.join(__dirname, 'submitted_reports');

// Ensure reports directory exists (run once on server start)
fs.mkdir(REPORTS_STORAGE_DIR, { recursive: true })
  .then(() => console.log(`Report storage directory ensured: ${REPORTS_STORAGE_DIR}`))
  .catch(err => console.error("Could not create report storage directory:", err));

// --- API Endpoint to trigger automation ---
// This matches the endpoint called by ReviewSubmitScreen.tsx
const API_ROUTE = '/api/start-fda-automation';

app.post(API_ROUTE, async (req, res) => {
    const submissionData = req.body; // Expects SubmissionPayload structure from types.ts
    const timestamp = new Date().toISOString();
    const dateForFile = timestamp.split('T')[0]; // Get YYYY-MM-DD part
    // Create a unique filename using timestamp and maybe part of user ID if safe
    // Using Date.now() for uniqueness is generally safer than userId in filenames
    const filename = `report_${dateForFile}_${Date.now()}.json`;
    const filePath = path.join(REPORTS_STORAGE_DIR, filename);
    
    console.log(`[${timestamp}] POST ${API_ROUTE} - Request received.`);

    // Basic Validation (Optional but recommended)
    if (!submissionData || typeof submissionData !== 'object' || !submissionData.problemDescription || !submissionData.reporterFirstName) {
        console.error(`[${timestamp}] Invalid or missing core data in request body.`);
        return res.status(400).json({ success: false, message: 'Bad Request: Missing or invalid core submission data.' });
    }
    
        // --- Save the Received Data to JSON File ---
        try {
            await fs.writeFile(filePath, JSON.stringify(submissionData, null, 2), 'utf8');
            console.log(`[${timestamp}] Report data successfully saved to: ${filePath}`);
        } catch (fileError) {
            console.error(`[${timestamp}] !!! FAILED TO SAVE REPORT DATA to ${filePath}:`, fileError);
            // Decide if you want to stop processing or just log the error and continue
            // For now, we'll log and continue to the automation attempt.
        }
    
    // Log warnings but proceed if these flags are missing/false (adjust if they should be errors)
    if (submissionData.attested !== true) { console.warn(`[${timestamp}] Request received without attestation.`); }
    if (!submissionData.phoneNumberVerified) { console.warn(`[${timestamp}] Request received without phone number verification.`); }

    // --- Trigger Automation ---
    try {
        console.log(`[${timestamp}] Starting FDA form automation process...`);

        // Call the imported Puppeteer function directly, passing the received data.
        // The server waits for the Puppeteer function to complete or throw an error.
        await automateFdaForm(submissionData);

        console.log(`[${timestamp}] Puppeteer automation function completed waiting period.`);
        // Send success response *after* automation finishes its waiting period
        // Note: This confirms the script ran its course, not necessarily that the FDA submission was successful (due to manual CAPTCHA step)
        res.status(200).json({
            success: true,
            message: 'FDA report automation process initiated and completed waiting period.',
        });

    } catch (error) {
        // Catch errors thrown by automateFdaForm
        console.error(`[${timestamp}] Error during FDA form automation:`, error.message);
        // Send a server error response back to the React Native app
        res.status(500).json({
            success: false,
            message: 'Internal Server Error: Failed during FDA form automation.',
            // error: error.message // Avoid sending detailed internal errors in production
        });
    }
});

// --- Simple Root Route for Testing Server ---
app.get('/', (req, res) => {
    res.send('FDA Automation Backend is running!');
});


// --- Start the Server ---
const PORT = process.env.PORT || 3000;
app.listen(PORT, '0.0.0.0', () => { // Listen on 0.0.0.0 for local network access
    console.log(`\n🚀 FDA Automation Backend Server is listening on port ${PORT}`);
    const networkInterfaces = os.networkInterfaces();
    console.log("   Access URLs:");
    console.log(`   - Localhost: http://localhost:${PORT}`);
    Object.keys(networkInterfaces).forEach(ifaceName => {
        networkInterfaces[ifaceName]?.forEach(iface => { // Added optional chaining for safety
            if (iface.family === 'IPv4' && !iface.internal) {
                // Log the IP address needed by the React Native app
                console.log(`   - Network (${ifaceName}): http://${iface.address}:${PORT}`);
            }
        });
    });
    console.log(`\n   API Endpoint for App: POST http://<Network IP>:${PORT}${API_ROUTE}`);
    console.log(`   Report JSON files will be saved in: ${REPORTS_STORAGE_DIR}`);
    console.log("   (Ensure firewall allows connections on port " + PORT + ")");
    console.log("   Press Ctrl+C to stop the server.\n");
});
