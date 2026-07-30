// automation/fdaAutomator.js
const puppeteer = require('puppeteer-extra'); // Use puppeteer-extra
const StealthPlugin = require('puppeteer-extra-plugin-stealth'); // Use stealth plugin
const fs = require('fs'); // Need fs for audio files
const { SpeechClient } = require('@google-cloud/speech'); // Google Cloud Speech
const axios = require('axios'); // To download audio
const ffmpeg = require('fluent-ffmpeg'); // To convert audio
const ffmpegStatic = require('ffmpeg-static'); // Path to ffmpeg binary
const path = require('path')

// Configure puppeteer-extra and ffmpeg
puppeteer.use(StealthPlugin());
ffmpeg.setFfmpegPath(ffmpegStatic); // Point fluent-ffmpeg to the binary


// ALL selectors and navigation flow on the live FDA site.
const FDA_INDEX_URL = 'https://www.accessdata.fda.gov/scripts/medwatch/index.cfm';
const SELECTORS = {
    // --- Navigation ---
    consumerReportLink: 'a[href*="consumer.reporting1"]',       
    startReportButton: 'input[type="submit"][value="Start Report"]', 
    nextButtonPage1: 'input[name="Next"][value="Next"]',          
    nextButtonPage2: 'input[name="Next"][value="Next"]',          
    nextButtonPage3: 'input[name="Next"][value="Next"]',          
    nextButtonPage5: 'input[name="Next"][value="Next"]',          
    finalSubmitButton: '#formSubmit',                             

    // --- Page 1: About Problem ---
    problemDescription: '#whatHappened',       
    problemDate: '#eventDate',                 
    problemCauseProduct: '#productProblem',    
    additionalComments: '#relevantTests',      

    // --- Page 2: About Product ---
    reportIsAboutCosmetic: '#cosmetic',             
    reportIsAboutSupplement: '#dietary',            
    reportIsAboutFood: '#foodOrMedicalFood',        
    reportIsAboutOther: '#otherFoodDietOrCosmetic', 
    productName: '#name_1',                         
    productExpirationDate: '#expirationDate_1',     
    productSpecifications: '#manufacturer_1',       

    // --- Page 3: About Patient ---
    patientInitials: '#patientInitials',             
    patientSexMale: '#patientSex_male',              
    patientSexFemale: '#patientSex_female',          
    patientAge: '#ageAtIncident',                    
    patientDob: '#dobDate',                          
    patientKnownMedicalConditionsOrAllergies: '#medicalConditions', 

    // --- Page 5: About Reporter ---
    reporterFirstName: '#firstName',                 
    reporterLastName: '#lastName',                   
    reporterEmail: '#emailAddress',                  
    reporterEmailConfirm: '#confirmEmailAddress',    
    reporterPhone: '#phoneNumber',                   

    // --- Page 6 (CAPTCHA) ---
    // Iframe containing the "I'm not a robot" checkbox
    recaptchaCheckboxIframeSelector: 'iframe[title="reCAPTCHA"]', // (Often uses title) or iframe[src*="api2/anchor"]
    // The checkbox element itself inside the first iframe
    recaptchaCheckboxSelector: '#recaptcha-anchor', // (Often uses this ID) or .recaptcha-checkbox-border
    // Iframe containing the audio/image challenge that appears *after* clicking checkbox
    recaptchaChallengeIframeSelector: 'iframe[src*="api2/bframe"]', // (Often uses bframe in src)
    // Audio button inside the challenge iframe
    recaptchaAudioButtonSelector: '#recaptcha-audio-button', 
    // Audio source element inside the challenge iframe
    recaptchaAudioSourceSelector: '#audio-source', 
    // Text input for audio response inside the challenge iframe
    recaptchaAudioResponseInputSelector: '#audio-response', 
    // Verify button inside the challenge iframe
    recaptchaVerifyButtonSelector: '#recaptcha-verify-button', 
};
// --- End Critical Selector Definitions ---

// Helper function for delay
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

/**
 * Helper function to safely interact with page elements.
 */
async function safeInteraction(page, interactionType, selector, value = null) {
    if (!selector) { console.warn(`Selector is missing for interaction type ${interactionType}`); return; }
    if (interactionType !== 'click' && (value === null || value === undefined || value === '')) { return; }
    try {
        await page.waitForSelector(selector, { timeout: 10000, visible: true });
        switch (interactionType) {
            case 'type':
                 const isInputOrTextarea = await page.evaluate((sel) => {
                     const el = document.querySelector(sel);
                     return el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;
                 }, selector);
                 if (isInputOrTextarea) {
                     try { await page.click(selector, { delay: 30 }); } catch(clickErr) { console.warn(`Minor issue clicking before typing ${selector}: ${clickErr.message.split('\n')[0]}`)}
                 }
                await page.type(selector, String(value), { delay: 40 + Math.random()*60 });
                console.log(`Typed "${String(value).substring(0,20)}..." into ${selector}`);
                break;
            case 'select':
                await page.select(selector, String(value));
                console.log(`Selected in ${selector}`); break;
            case 'click':
                await new Promise(r => setTimeout(r, 60 + Math.random()*110));
                await page.click(selector);
                console.log(`Clicked ${selector}`); break;
            default: console.warn(`Unknown interaction type: ${interactionType}`);
        }
        await new Promise(r => setTimeout(r, 60));
    } catch (e) { console.warn(`Could not perform ${interactionType} on selector "${selector}": ${e.message.split('\n')[0]}`); }
}


/**
 * Attempts to solve the reCAPTCHA audio challenge.
 * @param {import('puppeteer').Page} page - The main Puppeteer page object.
 * @param {SpeechClient} speechClient - Initialized Google Speech client.
 */
async function solveAudioChallenge(page, speechClient) {
  let audioPath = 'captcha_audio.mp3'; // Use fixed names for simplicity in cleanup
  let flacPath = 'captcha_audio.flac';
  try {
    console.log('Starting audio challenge solution...');

    // 1. Wait for and switch to challenge iframe
    console.log(`Waiting for challenge iframe: ${SELECTORS.recaptchaChallengeIframeSelector}`);
    await page.waitForSelector(SELECTORS.recaptchaChallengeIframeSelector, { timeout: 10000 });
    const challengeFrame = page.frames().find(f => f.url().includes('api2/bframe')); // Find by URL part
    if (!challengeFrame) throw new Error('Challenge iframe (bframe) not found');
    console.log('Challenge iframe found.');

    // 2. Click audio challenge button
    console.log(`Waiting for audio button: ${SELECTORS.recaptchaAudioButtonSelector}`);
    await challengeFrame.waitForSelector(SELECTORS.recaptchaAudioButtonSelector, { visible: true, timeout: 10000 });
    await challengeFrame.click(SELECTORS.recaptchaAudioButtonSelector);
    console.log('Clicked audio button.');
    await delay(2000); // Wait for audio source to load

    // 3. Get audio URL
    console.log(`Waiting for audio source element: ${SELECTORS.recaptchaAudioSourceSelector}`);
    await challengeFrame.waitForSelector(SELECTORS.recaptchaAudioSourceSelector, { timeout: 10000 });
    const audioUrl = await challengeFrame.evaluate((sel) => {
      const audioSrc = document.querySelector(sel); // Use querySelector inside evaluate
      if (!audioSrc) throw new Error(`Audio source element (${sel}) not found in challenge iframe`);
      return audioSrc.src;
    }, SELECTORS.recaptchaAudioSourceSelector); // Pass selector to evaluate
    console.log('Downloading audio from:', audioUrl);

    // 4. Download audio file
    const writer = fs.createWriteStream(audioPath);
    const audioResponse = await axios({ method: 'get', url: audioUrl, responseType: 'stream', timeout: 15000 });
    audioResponse.data.pipe(writer);
    await new Promise((resolve, reject) => {
      writer.on('finish', resolve);
      writer.on('error', reject);
      setTimeout(() => reject(new Error('Audio download timeout')), 20000); // Add timeout
    });
    console.log('Audio downloaded.');

    // 5. Convert MP3 to FLAC using fluent-ffmpeg
    console.log('Converting audio to FLAC...');
    await new Promise((resolve, reject) => {
      ffmpeg(audioPath)
        .toFormat('flac')
        .audioChannels(1) // Mono channel
        .audioFrequency(16000) // Sample rate required by Google Speech API
        .on('error', (err) => reject(new Error(`FFmpeg error: ${err.message}`)))
        .on('end', () => { console.log('Conversion finished.'); resolve(); })
        .save(flacPath);
    });

    // 6. Read FLAC file and send to Google Speech-to-Text
    console.log('Sending audio to Google Cloud Speech...');
    const audioFile = fs.readFileSync(flacPath);
    const audioBytes = audioFile.toString('base64');
    const [recognitionResponse] = await speechClient.recognize({
      audio: { content: audioBytes },
      config: {
        encoding: 'FLAC',
        sampleRateHertz: 16000,
        languageCode: 'en-US',
      },
    });

    // 7. Process transcription
    console.log('Raw Speech recognition results:', JSON.stringify(recognitionResponse.results, null, 2));
    if (!recognitionResponse.results || recognitionResponse.results.length === 0 || !recognitionResponse.results[0].alternatives || recognitionResponse.results[0].alternatives.length === 0) {
        throw new Error('No transcription received from Google Speech API.');
    }
    const transcription = recognitionResponse.results
      .map(result => result.alternatives[0].transcript)
      .join(' ')
      .trim();

    console.log('Full transcription:', transcription);
    if (!transcription) throw new Error('Empty transcription received.');

    // 8. Submit the transcription
    console.log(`Typing transcription into: ${SELECTORS.recaptchaAudioResponseInputSelector}`);
    await challengeFrame.waitForSelector(SELECTORS.recaptchaAudioResponseInputSelector, { visible: true, timeout: 5000 });
    await challengeFrame.type(SELECTORS.recaptchaAudioResponseInputSelector, transcription, { delay: 50 + Math.random()*50 });
    await delay(500);
    console.log(`Clicking verify button: ${SELECTORS.recaptchaVerifyButtonSelector}`);
    await challengeFrame.waitForSelector(SELECTORS.recaptchaVerifyButtonSelector, { visible: true, timeout: 5000 });
    await challengeFrame.click(SELECTORS.recaptchaVerifyButtonSelector);
    await delay(2500); // Wait for verification result

    console.log('Audio challenge submitted.');
    return transcription;

  } catch (error) {
    console.error("Error in solveAudioChallenge:", error);
    throw error; // Re-throw to be caught by main try/catch
  } finally {
    // Cleanup temporary audio files
    try {
        if (fs.existsSync(audioPath)) fs.unlinkSync(audioPath);
        if (fs.existsSync(flacPath)) fs.unlinkSync(flacPath);
        console.log("Cleaned up temporary audio files.");
    } catch (cleanupError) {
        console.warn("Warning: Could not clean up temporary audio files:", cleanupError);
    }
  }
}


/**
 * Main automation function.
 */
async function automateFdaForm(formData) {
    console.log('--- automateFdaForm received formData: ---');
    console.log(JSON.stringify(formData, null, 2));
    console.log('-----------------------------------------');

    console.log('🚀 Starting FDA form automation [Audio Bypass Testing Mode]...');
    let browser = null;
    let page = null;

    // Initialize Google Speech client here
    // Ensure GOOGLE_APPLICATION_CREDENTIALS env var is set
    const keyFilePath = path.join(__dirname, 'google-cloud-key.json'); // Use path.join for cross-platform compatibility
    console.log(`Attempting to load Google Cloud credentials from: ${keyFilePath}`);

    // Check if file exists before initializing
    if (!fs.existsSync(keyFilePath)) {
        throw new Error(`Key file not found at specified path: ${keyFilePath}. Please ensure 'google-cloud-key.json' is in the 'automation' folder.`);
    }
    
    let speechClient;
    try {
        speechClient = new SpeechClient(
            { keyFilename: keyFilePath } // Use the path to the key file
        );
        console.log("Google Speech client initialized.");
    } catch(e) {
        console.error("❌ ERROR: Failed to initialize Google Speech client. Ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set correctly.", e);
        throw new Error("Google Speech client initialization failed.");
    }

    const { /* ... destructure formData ... */
        problemDescription, problemDate, problemCause, productPurchaseLocation,
        reportIsAbout, productName, productExpirationDate, specifications,
        patientInitials, patientSex, patientKnownMedicalConditionsOrAllergies,
        reporterFirstName, reporterLastName, reporterEmail,
        phoneNumberVerified, attested
    } = formData;

    try {
        browser = await puppeteer.launch({
            headless: false, // MUST be false to see CAPTCHA interaction
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1366,768'],
            timeout: 60000
        });
        page = await browser.newPage();
        await page.setViewport({ width: 1366, height: 768 });
        await page.setUserAgent(
             'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36' // Example User Agent
        );

        // --- Navigation & Form Filling ---
        console.log(`Navigating to FDA MedWatch index: ${FDA_INDEX_URL}`);
        await page.goto(FDA_INDEX_URL, { waitUntil: 'load', timeout: 60000 });
        console.log('Index page loaded.');
        // 1. Click Consumer Link
        if (!SELECTORS.consumerReportLink) throw new Error("Selector for consumerReportLink missing!");
        await Promise.all([ page.waitForNavigation({ waitUntil: 'load', timeout: 60000 }), safeInteraction(page, 'click', SELECTORS.consumerReportLink) ]);
        console.log('Navigated to consumer reporting start page.');
        // 2. Optional: Click Start Report Button
        if (SELECTORS.startReportButton) {
             console.log(`Checking for and clicking start button: ${SELECTORS.startReportButton}`);
             try {
                  await page.waitForSelector(SELECTORS.startReportButton, { timeout: 5000, visible: true });
                  await Promise.all([ page.waitForNavigation({ waitUntil: 'load', timeout: 60000 }), safeInteraction(page, 'click', SELECTORS.startReportButton) ]);
                  console.log('Clicked Start Report button.');
             } catch(e) { console.log('Start Report button not found or clickable, proceeding...'); }
        }
        // --- Page 1 ---
        console.log('Filling Page 1...');
        await safeInteraction(page, 'type', SELECTORS.problemDescription, problemDescription);
        if (problemDate && SELECTORS.problemDate) { const digits = problemDate.replace(/\//g, ''); await safeInteraction(page, 'click', SELECTORS.problemDate); await safeInteraction(page, 'type', SELECTORS.problemDate, digits); }
        await safeInteraction(page, 'type', SELECTORS.additionalComments, `Purchased at: ${productPurchaseLocation}`);
        await safeInteraction(page, 'click', SELECTORS.problemCauseProduct);
        await Promise.all([ page.waitForNavigation({ waitUntil: 'load', timeout: 60000 }), safeInteraction(page, 'click', SELECTORS.nextButtonPage1) ]);
        console.log('Navigated to Page 2.');
        // --- Page 2 ---
        console.log('Filling Page 2...');
        if (reportIsAbout === 'Cosmetic') await safeInteraction(page, 'click', SELECTORS.reportIsAboutCosmetic); else if (reportIsAbout === 'DietarySupplement') await safeInteraction(page, 'click', SELECTORS.reportIsAboutSupplement); else if (reportIsAbout === 'FoodMedicalFood') await safeInteraction(page, 'click', SELECTORS.reportIsAboutFood); else if (reportIsAbout === 'Other') await safeInteraction(page, 'click', SELECTORS.reportIsAboutOther);
        await safeInteraction(page, 'type', SELECTORS.productName, productName);
        if (productExpirationDate && SELECTORS.productExpirationDate) { const digits = productExpirationDate.replace(/\//g, ''); await safeInteraction(page, 'click', SELECTORS.productExpirationDate); await safeInteraction(page, 'type', SELECTORS.productExpirationDate, digits); }
        await safeInteraction(page, 'type', SELECTORS.productSpecifications, specifications);
        await Promise.all([ page.waitForNavigation({ waitUntil: 'load', timeout: 60000 }), safeInteraction(page, 'click', SELECTORS.nextButtonPage2) ]);
        console.log('Navigated to Page 3.');
        // --- Page 3 ---
        console.log('Filling Page 3...');
        await safeInteraction(page, 'type', SELECTORS.patientInitials, patientInitials);
        if (patientSex === 'Male') await safeInteraction(page, 'click', SELECTORS.patientSexMale); else if (patientSex === 'Female') await safeInteraction(page, 'click', SELECTORS.patientSexFemale);
        // await safeInteraction(page, 'type', SELECTORS.patientAge, patientAgeOrDob); // Removed Age/DOB
        // await safeInteraction(page, 'type', SELECTORS.patientDob, patientAgeOrDob); // Removed Age/DOB
        await safeInteraction(page, 'type', SELECTORS.patientKnownMedicalConditionsOrAllergies, patientKnownMedicalConditionsOrAllergies);
        await Promise.all([ page.waitForNavigation({ waitUntil: 'load', timeout: 60000 }), safeInteraction(page, 'click', SELECTORS.nextButtonPage3) ]);
        console.log('Navigated to Page 5.');
        // --- Page 5 ---
        console.log('Filling Page 5...');
        await safeInteraction(page, 'type', SELECTORS.reporterFirstName, reporterFirstName);
        await safeInteraction(page, 'type', SELECTORS.reporterLastName, reporterLastName);
        await safeInteraction(page, 'type', SELECTORS.reporterEmail, reporterEmail);
        await safeInteraction(page, 'type', SELECTORS.reporterEmailConfirm, reporterEmail);
        await safeInteraction(page, 'type', SELECTORS.reporterPhone, phoneNumberVerified);
        await Promise.all([ page.waitForNavigation({ waitUntil: 'load', timeout: 60000 }), safeInteraction(page, 'click', SELECTORS.nextButtonPage5) ]);
        console.log('Navigated to Page 6 (Review/Submit).');
        // --- End Form Filling ---


        // --- Page 6: Review & Submit ---
        console.log('Reached final Review/Submit page.');

        // --- Attempt reCAPTCHA Audio Bypass ---
        let captchaSolved = false;
        const maxAttempts = 2;
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                console.log(`Attempt ${attempt} to solve reCAPTCHA...`);
                console.log(`Waiting for checkbox iframe: ${SELECTORS.recaptchaCheckboxIframeSelector}`);
                await page.waitForSelector(SELECTORS.recaptchaCheckboxIframeSelector, { timeout: 15000 });
                const recaptchaFrame = page.frames().find(f => f.url().includes('api2/anchor'));
                if (!recaptchaFrame) throw new Error('reCAPTCHA checkbox iframe not found');

                console.log(`Waiting for checkbox: ${SELECTORS.recaptchaCheckboxSelector}`);
                await recaptchaFrame.waitForSelector(SELECTORS.recaptchaCheckboxSelector, { visible: true, timeout: 10000 });
                await recaptchaFrame.click(SELECTORS.recaptchaCheckboxSelector);
                console.log('Clicked reCAPTCHA checkbox.');
                await delay(3000);

                const isSolved = await recaptchaFrame.evaluate((sel) => {
                    const el = document.querySelector(sel);
                    return el && el.getAttribute('aria-checked') === 'true';
                }, SELECTORS.recaptchaCheckboxSelector);

                if (isSolved) { console.log('CAPTCHA solved by checkbox click!'); captchaSolved = true; break; }

                console.log('Checkbox click did not solve. Checking for challenge iframe...');
                await page.waitForSelector(SELECTORS.recaptchaChallengeIframeSelector, { timeout: 5000 });
                console.log('Challenge iframe detected - attempting audio solution...');
                await solveAudioChallenge(page, speechClient);

                await delay(2000);
                 const isSolvedAfterAudio = await recaptchaFrame.evaluate((sel) => {
                    const el = document.querySelector(sel);
                    return el && el.getAttribute('aria-checked') === 'true';
                }, SELECTORS.recaptchaCheckboxSelector);

                if (isSolvedAfterAudio) { console.log('CAPTCHA successfully solved via audio!'); captchaSolved = true; break; }
                else { console.warn(`Attempt ${attempt}: Audio challenge did not result in verified state.`); if (attempt < maxAttempts) await delay(3000); }

            } catch (err) {
                console.error(`Attempt ${attempt} failed:`, err.message);
                if (attempt < maxAttempts) { console.log('Waiting before retry...'); await delay(3000); }
            }
        } // End of attempt loop

        if (!captchaSolved) { throw new Error(`Failed to solve CAPTCHA after ${maxAttempts} attempts`); }
        // --- End reCAPTCHA Handling ---


        // --- Stop Here for Testing ---
        console.log('✅ CAPTCHA handling completed successfully.');
        console.log('ℹ️ Stopping script before final submission as requested for testing.');


    } catch (error) {
        console.error('❌ Puppeteer/CAPTCHA automation error:', error);
        if (page) { /* ... screenshot logic ... */ }
        throw error; // Re-throw error
    } finally {
        if (browser) {
            console.log("Browser will close shortly...");
            await new Promise(r => setTimeout(r, 10000)); // Keep open briefly
            await browser.close();
            console.log('Browser closed.');
        }
    }
}

// Export the function
module.exports = { automateFdaForm };
