import os
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests as req
from io import StringIO
from Bio.PDB import PDBParser, MMCIFIO
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv()

# --- Configuration ---
CLOUDFLARE_SECRET_KEY = os.environ.get("CLOUDFLARE_SECRET_KEY")

# Safety check: Ensure the secret key is set in the production environment
if not CLOUDFLARE_SECRET_KEY:
    # This will cause the app to fail on startup if the key is not set on Render, which is a good safety measure.
    raise ValueError("FATAL ERROR: CLOUDFLARE_SECRET_KEY environment variable not set.")

TEMP_DIR = 'temp_files'
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- Flask App Initialization ---
app = Flask(__name__)
# In production, you might want to restrict origins to your actual frontend domain
# For example: CORS(app, resources={r"/api/*": {"origins": "https://your-frontend-domain.com"}})
CORS(app, resources={r"/api/*": {"origins": "*"}}) 

# --- PDB to CIF Conversion Logic ---
def convert_pdb_to_cif(pdb_data_string: str, structure_id: str = "protein"):
    try:
        pdb_parser = PDBParser(QUIET=True)
        pdb_file = StringIO(pdb_data_string)
        structure = pdb_parser.get_structure(structure_id, pdb_file)
        
        cif_io = MMCIFIO()
        cif_io.set_structure(structure)
        
        output_cif = StringIO()
        cif_io.save(output_cif)
        return output_cif.getvalue()

    except Exception as e:
        print(f"Error during PDB to CIF conversion: {e}")
        return None

# --- API Endpoints ---
@app.route('/api/convert', methods=['POST'])
def handle_conversion():
    """
    Handles the main conversion request from the frontend with CAPTCHA verification.
    """
    # 1. Verify Cloudflare Turnstile CAPTCHA (This section is now ACTIVE)
    turnstile_token = request.form.get('cf-turnstile-response')
    if not turnstile_token:
        return jsonify({"success": False, "error": "CAPTCHA token missing. Please refresh the page."}), 403

    verification_response = req.post(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data={"secret": CLOUDFLARE_SECRET_KEY, "response": turnstile_token},
    )
    outcome = verification_response.json()

    if not outcome.get("success"):
        print(f"CAPTCHA verification failed. Reason: {outcome.get('error-codes', 'Unknown')}")
        return jsonify({"success": False, "error": "CAPTCHA verification failed. Please try again."}), 403

    # 2. Get PDB data from either file upload or text area
    pdb_data = ""
    if 'file' in request.files and request.files['file'].filename != '':
        pdb_file = request.files['file']
        pdb_data = pdb_file.read().decode('utf-8')
    elif 'pdb_data' in request.form and request.form['pdb_data'].strip() != '':
        pdb_data = request.form['pdb_data']
    else:
        return jsonify({"success": False, "error": "No PDB data provided. Please upload a file or paste data."}), 400

    # 3. Perform the conversion
    cif_result = convert_pdb_to_cif(pdb_data)

    if not cif_result:
        return jsonify({"success": False, "error": "Conversion failed. The provided data may not be a valid PDB format."}), 400

    # 4. Save the result to a temporary file and prepare the response
    unique_filename = f"{uuid.uuid4()}.cif"
    output_path = os.path.join(TEMP_DIR, unique_filename)
    with open(output_path, "w") as f:
        f.write(cif_result)

    # 5. Return success with CIF data for preview and a download URL
    return jsonify({
        "success": True,
        "cif_data": cif_result,
        "download_url": f"/api/download/{unique_filename}"
    })

@app.route('/api/download/<filename>')
def download_converted_file(filename):
    """
    Serves the converted file for download.
    """
    return send_from_directory(TEMP_DIR, filename, as_attachment=True)

# --- Main Entry Point ---
if __name__ == '__main__':
    # This part is for local development only. Gunicorn is used in production.
    app.run(port=5000, debug=True)
