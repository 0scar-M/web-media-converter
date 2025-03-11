from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
import io
import os
import sqlite3 as sql
import subprocess
import time
import tempfile
from typing import List
import uuid
import zipfile

# Load environment variables
load_dotenv()

# Define global variables
frontend_url = f"http://{os.getenv("HOST_NAME")}"
media_formats = { # All suported formats for each media type.
    "image": ("BMP", "GIF", "JPG", "PNG", "SVG", "TIF", "WEBP"), 
    "video": ("AVI", "FLV", "MKV", "MOV", "MP4", "WMV"), 
    "audio": ("AAC", "FLAC", "MP3", "OGG", "WAV", "WMA")
}
format_aliases = { # Some formats have multiple names, this provides a way to correct them.
    "JPG": ("JPEG", "JPE"), 
    "SVG": ("SVGZ"), 
    "TIF": ("TIFF"),
    "MP4": ("M4V"), 
    "AAC": ("M4A"), 
    "OGG": ("OGA")
}
valid_formats = [x for y in media_formats.values() for x in y] # Set valid_formats to list of all valid formats
invalid_conversions = [("FLV", "MKV")]
invalid_conversions = [(x, "SVG") for x in media_formats["image"] if x != "SVG"] # Cannot convert raster to vector
invalid_conversions += [(x, "TIF") for x in media_formats["image"] if x != "TIF"]

# Configure FastAPI app
app = FastAPI()

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


class DB:
    "Manages the backend's interaction with the database."

    def __init__(self):
        "Opens database connection."
        self.timeout_secs = 600 # 10 mins
        self.path = os.getenv("DATABASE_PATH") # get database path from environment variable. See docker-compose.yml
        self.conn = sql.connect(self.path, check_same_thread=False)
        self.cursor = self.conn.cursor()
    
    def check_expired_sessions(self):
        """
        Removes any expired sessions if session.last_changed_at < current time - self.timeout_secs
        """
        expired_time = time.time() - self.timeout_secs
        try:
            session_ids = self.cursor.execute("SELECT session_id FROM sessions WHERE last_changed_at < ?", (expired_time,)).fetchall()
            for x in session_ids:
                self.cursor.execute("DELETE FROM sessions WHERE session_id=?", (x[0],))
                self.cursor.execute("DELETE FROM files WHERE session_id=?", (x[0],))
                self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise_error(e, "removing expired session from database")

    def query(self, query_body: str, error_action: str, *query_params: tuple):
        """
        Executes a query on the database, returns the response and commits the changes.
        query_body = query to be executed.
        error_action = what this query does, used for descriptive error msgs.
        *query_params = parameterized parameters for query.
        """
        try:
            self.check_expired_sessions()
            self.cursor.execute(query_body, query_params)
            result = self.cursor.fetchall()
            self.conn.commit()
            return result
        except Exception as e:
            self.conn.rollback()
            raise_error(e, error_action)
    
    def close(self):
        "Terminates the database connection."
        self.conn.close()

def raise_error(error, error_action, code=500):
    "Raises an HTTPException if result is an Exception."
    if issubclass(type(error), Exception):
        if error_action:
            raise HTTPException(status_code=code, detail=f"{error} while {error_action}")
        else:
            raise HTTPException(status_code=code, detail=error)

def correct_format(format: str):
    """
    Returns the file format corrected to its standard form based on format_aliases.
    If format is not valid, or no aliases exist, it is returned unchanged.
    """
    
    format = format.upper()

    if format in format_aliases: # Check if format is already correct
        return format
    
    for correct_format, aliases in format_aliases.items():
        if format in aliases:
            return correct_format
    
    return format # If no match is found, return the original format

def is_valid_conversion(conversion: tuple[str, str]):
    "Returns True if conversion is valid, False if conversion is invalid."
    
    conversion = tuple([correct_format(x) for x in conversion]) # correct conversion formats
    
    if [x in valid_formats for x in conversion] == [True, True] and conversion not in invalid_conversions and get_media_type(conversion[0]) == get_media_type(conversion[1]):
        return True
    else:
        return False

def get_media_type(format):
    "Returns the media type (image, video or audio) of a given format."

    return list(media_formats.keys())[list(media_formats.values()).index([x for x in media_formats.values() if format in x][0])]

def get_db():
    "Dependency function"

    db = DB()
    try:
        yield db
    finally:
        db.close()

@app.post("/upload/")
async def upload_file(session_id: str = Query(...), files: List[UploadFile] = File(...), db: DB = Depends(get_db)):
    """
    Adds entry to files table.
    If session_id = new, then a new uuid will be returned and a new entry will be created in the sessions table for the file.
    If session_id != new and is already in the db, then it will still be returned and the entry for that id will be updated with the new file.
    """
    if session_id == "new":
        session_id = str(uuid.uuid4())
        new_session = True
    else: new_session = False

    uploaded_files_json = []
    session_ids = [x[0] for x in db.query("SELECT session_id FROM files;", "getting list of session_ids from database")] # list of tuples of strings -> list of strings

    if new_session:
        db.query("INSERT INTO sessions VALUES (?, ?);", "inserting session data into database", session_id, time.time()) # Insert session data
    elif session_id in session_ids:
        db.query("UPDATE sessions SET last_changed_at=? WHERE session_id=?;", "updating session data in database", time.time(), session_id) # Update session data
        db.query("DELETE FROM files WHERE session_id=?;", "removing old files from database", session_id) # Remove old files
    else:
        raise HTTPException(status_code=404, detail=f"Invalid session_id value '{session_id}'")
    
    for file in files:
        file_name = file.filename
        file_format = correct_format(file.filename.split(".")[-1].upper())
        file_contents = await file.read()
        file_id = file.filename+"|"+session_id
        uploaded_files_json.append({"file_name": file_name, "file_id": file_id})

        if file_format not in valid_formats:
            raise HTTPException(status_code=400, detail=f"Invalid file format '{file_format}'")
        
        # Upload files to db
        db.query("INSERT INTO files VALUES (?, ?, ?, ?, ?, 0);", "inserting file data into database", file_id, session_id, file_name, file_format, file_contents)
    
    return {
        "uploaded_files": uploaded_files_json, 
        "session_id": session_id
    }

@app.patch("/convert/")
async def convert_file(session_id: str = Query(...), to_format: str = Query(...), db: DB = Depends(get_db)):
    "Converts file in database to desired format."

    # Validate to_format
    to_format = correct_format(to_format)
    if to_format not in valid_formats:
        raise HTTPException(status_code=404, detail=f"Invalid to_format: {to_format}")

    # Get file to convert contents and other data from db, and validate session_id
    files = db.query("SELECT file_id, name, format, contents FROM files WHERE session_id=? AND converted=0", "getting file from database", session_id)
    if not files:
        raise HTTPException(status_code=404, detail=f"File not found for session_id: '{session_id}'")

    converted_files_json = []

    for f in files:
        file_id = f[0]
        name = f[1]
        new_name = name.split(".")[0]+"."+(to_format.lower())
        conversion = (f[2], to_format)
        contents = f[3]
        converted_files_json.append({"file_name": new_name, "file_id": file_id})

        if is_valid_conversion(conversion):
            input_io = io.BytesIO(contents)
            output_io = io.BytesIO()

            # Create temporary files for the conversion input and output
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{conversion[0].lower()}") as input_temp:
                input_temp.write(input_io.getvalue())
                input_temp.flush()
                input_temp_name = input_temp.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{conversion[1].lower()}") as output_temp:
                output_temp_name = output_temp.name
        else:
            raise HTTPException(status_code=400, detail=f"Invalid file conversion '{' to '.join(conversion)}'")

        try:
            # Construct the command
            command = ["ffmpeg", "-nostdin", "-y", "-i", input_temp_name, output_temp_name]

            # Run the ffmpeg process
            process = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60  # Timeout after 60 seconds
            )
        except subprocess.TimeoutExpired:
            raise_error("FFMPEG process timed out", "converting file")
        except Exception as e:
            raise_error(e, "converting file")

        # Check for errors
        if process.returncode != 0:
            raise_error(f"FFMPEG error: {process.stderr.decode()}", "converting file")
        else:
            # Read the output files from the temporary files into BytesIO objects
            with open(output_temp_name, 'rb') as output_temp:
                output_io = io.BytesIO(output_temp.read())
                output_io.name = new_name
                # Upload converted files into db
                db.query("UPDATE files SET name=?, contents=?, format=?, converted=1 WHERE file_id=?", "converting file in database", new_name, output_io.getvalue(), conversion[1], file_id)
            
            # Clean up temporary files
            os.remove(input_temp_name)
            os.remove(output_temp_name)
    
    db.query("UPDATE sessions SET last_changed_at=? WHERE session_id=?", "updating session data in database", time.time(), session_id)

    return {
        "converted_files": converted_files_json, 
        "session_id": session_id
    }

@app.get("/download/")
async def download_file(session_id: str = Query(...), db: DB = Depends(get_db)):
    "Returns all files for a given session_id."

    # Get file contents and other data from db
    files = db.query("SELECT name, contents, format FROM files WHERE session_id=? AND converted=1", "getting files from database", session_id)
    if not files:
        raise HTTPException(status_code=404, detail=f"File not found for session_id: '{session_id}'")

    if len(files) == 1:
        # Return single un-zipped file
        return Response(
            content=files[0][1], 
            media_type= f"{get_media_type(files[0][2])}/{files[0][2]}".lower(), 
            headers={"filename": files[0][0]}
        )
    else:
        files = [[name, io.BytesIO(contents)] for name, contents, format in files]
        # Return zipped files
        zip_output = io.BytesIO()
        
        # Create a zip file in the zip_output BytesIO and add files to it
        with zipfile.ZipFile(zip_output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
            # Add each file to the zip archive
            for name, contents in files:
                zip_file.writestr(name, contents.getvalue())
        
        zip_output.seek(0) # Reset pointer of BytesIO object to beginning

        return StreamingResponse(
            zip_output, 
            media_type="application/x-zip-compressed", 
            headers={"Content-Disposition": "attachment; filename=web-media-converter-converted-files.zip", 
                "filename":"web-media-converter-converted-files.zip"
            }
        )

@app.get("/supported-formats/")
async def supported_formats():
    "Returns all valid formats."

    return media_formats

@app.get("/supported-conversions/")
async def supported_conversions(format: str):
    "Returns all valid formats to convert to for a specific format if it is in valid_formats."

    format = correct_format(format)
    if format in valid_formats:
        same_media_type_formats = [x for x in media_formats.values() if format in x][0]
        return [x for x in same_media_type_formats if is_valid_conversion((format, x))]
    else:
        raise HTTPException(status_code=404, detail=f"Invalid format: {format}")

@app.get("/is-valid-conversion/")
async def is_valid_conversion_endpoint(from_format: str, to_format: str):
    "Returns True if file conversion from from_format to to_format is valid, False if not."

    from_format = correct_format(from_format)
    to_format = correct_format(to_format)
    return is_valid_conversion((from_format, to_format))
