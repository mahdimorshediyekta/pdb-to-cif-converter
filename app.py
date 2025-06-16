import os
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests as req
from io import StringIO
from Bio.PDB import PDBParser, MMCIFIO
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
# We still load the key, but we won't use it in the modified code.
CLOUDFLARE_SECRET_KEY = os.environ.get("CLOUDFLARE_SECRET_KEY")

TEMP_DIR = 'temp_files'
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- Flask App Initialization ---
app = Flask(__name__)
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
    Handles the main conversion request from the frontend.
    """
    # ==================== MODIFICATION START ====================
    # The entire Cloudflare Turnstile section below is commented out for testing.
    # To re-enable it, simply remove the '#' from the beginning of each line.
    #
    # # 1. Verify Cloudflare Turnstile CAPTCHA
    # turnstile_token = request.form.get('cf-turnstile-response')
    # if not turnstile_token:
    #     return jsonify({"success": False, "error": "CAPTCHA token missing."}), 403
    #
    # # The check for the secret key is also disabled for now.
    # if CLOUDFLARE_SECRET_KEY:
    #     verification_response = req.post(
    #         "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    #         data={"secret": CLOUDFLARE_SECRET_KEY, "response": turnstile_token},
    #     )
    #     outcome = verification_response.json()
    #
    #     if not outcome.get("success"):
    #         return jsonify({"success": False, "error": "CAPTCHA verification failed. Please try again."}), 403
    # ===================== MODIFICATION END =====================


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
    app.run(port=5000, debug=True)
