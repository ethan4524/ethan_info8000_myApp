from flask import *
import sqlite3
from werkzeug.security import generate_password_hash,check_password_hash
import uuid
import pandas as pd
from flask import request
import requests
from datetime import datetime
import csv
import io
import geopy.distance




app = Flask(__name__, static_folder='static', template_folder='templates')

weather_data = {
    "Code": [0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99],
    "Description": [
        "Clear sky", "Mainly clear", "Partly cloudy", "Overcast", "Fog", "Depositing rime fog",
        "Drizzle (light)", "Drizzle (moderate)", "Drizzle (dense)", "Freezing drizzle (light)",
        "Freezing drizzle (dense)", "Rain (slight)", "Rain (moderate)", "Rain (heavy)",
        "Freezing rain (light)", "Freezing rain (heavy)", "Snowfall (slight)", "Snowfall (moderate)",
        "Snowfall (heavy)", "Snow grains", "Rain showers (slight)", "Rain showers (moderate)",
        "Rain showers (violent)", "Snow showers (slight)", "Snow showers (heavy)", "Thunderstorm (slight/moderate)",
        "Thunderstorm (slight hail)", "Thunderstorm (heavy hail)"
    ]
}
# Create the DataFrame
weather_df = pd.DataFrame(weather_data)

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/logout')
def logout():
    return redirect('/')

@app.route('/')
def root():
    return render_template('login.html')

@app.route('/authenticate', methods=['POST'])
def authenticate():
    username = request.form['username']
    password = request.form['password']

    # Connect to the SQLite database
    con = sqlite3.connect('database.db')

    # Read entire database into a Pandas DataFrame (Is this a security issue? lol)
    df = pd.read_sql_query("SELECT * FROM userdata", con)

    # Close the database connection
    con.close()

    # Check if the user exists in the DataFrame and password is correct
    user = df[df['username'] == username]
    if not user.empty and check_password_hash(user.iloc[0]['password'], password):
        # Get the API key for the user
        api_key = user.iloc[0]['api_key']
        # Redirect to user home with username and API key
        print('api_key:' + str(api_key))
        return redirect(url_for('user_home', username=username, api_key=api_key))
    else:
        # User does not exist or password is incorrect
        return render_template('login.html', error_message="Invalid username or password. Please try again.")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Retrieve form data
        username = request.form['username']
        password = request.form['password']

        # Connect to the database
        with sqlite3.connect('database.db') as con:
            cursor = con.cursor()

            # Check if the username already exists
            cursor.execute("SELECT * FROM userdata WHERE username = ?", (username,))
            existing_user = cursor.fetchone()

            if existing_user:
                # Username already exists, return a response indicating failure
                return jsonify({'success': False, 'message': 'Username already exists'}), 400

            # Generate unique user ID and API key
            user_id = str(uuid.uuid4())
            api_key = str(uuid.uuid4())

            # Hash password
            hashed_password = generate_password_hash(password)

            # Insert user data into the database
            cursor.execute("INSERT INTO userdata (username, user_ID, password, api_key) VALUES (?, ?, ?, ?);", (username, user_id, hashed_password, api_key))

            # Commit the transaction
            con.commit()

        return jsonify({'success': True, 'message': 'Registration successful'}), 200

    return render_template('register.html')

@app.route('/user_home/<username>')
def user_home(username):
    api_key = request.args.get('api_key')
    return render_template('user_home.html', username=username, api_key=api_key)

@app.route('/download_data')
def download_data() :
    return render_template('/data_query')

@app.route('/success')
def success() :
    return render_template('/data_query')

def get_user_id(api_key):
    # Load the database table into a DataFrame
    df = pd.read_sql_query("SELECT * FROM userdata", sqlite3.connect('database.db'))
    
    # Filter the DataFrame to find the user_id associated with the provided API key
    user_id_series = df.loc[df['api_key'] == api_key, 'user_ID']
    
    if not user_id_series.empty:
        return user_id_series.iloc[0]  # Return the user_id if found
    else:
        return None  # Return None if no user_id found for the API key

@app.route('/report', methods=['POST'])
def report():
    # Extract form data
    api_key = request.form.get('api_key')
    description = request.form.get('description')
    lat = request.form.get('latitude')
    lon = request.form.get('longitude')
    submitter_ip = request.remote_addr
    user_id = get_user_id(api_key=api_key)
    
    # Check if file is included in the request
    if 'file' not in request.files:
        return 'No file part'
    
    file = request.files['file']
    
    if file.filename == '':
        return 'No selected file'

    # Save the file to the server
    file_path = 'uploads/' + file.filename
    file.save(file_path)

    # Make API call to OpenMeteo
    query = f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code'
    response = requests.get(query)
    data = response.json()

    # Parse the JSON response
    current_temperature = data['current']['temperature_2m']
    weather_code = data['current']['weather_code']

    # Interpret weather code
    weather_description = weather_df.loc[weather_df['Code'] == weather_code, 'Description'].values[0]

    # Characterize the Description using Google Gemini
    my_key = 'AIzaSyD7-K_u2P-9FU1VhOiJG3egwPGUIDfR2XM'
    host = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent'
    headers = {'Content-Type': 'application/json'}
    question = f"Characterize the following description as normal, offensive, or wildcard: {description}"

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": str(question)
                    }
                ]
            }
        ]
    }
    params = {'key': my_key}

    res = requests.post(host, headers=headers, json=data, params=params)
    characterization = ''
    if res.status_code == 200:
        response_json = res.json()
        characterization = response_json["candidates"][0]["content"]["parts"][0]["text"]
    else:
        characterization = 'Unable to process characterization'

    # Store data in the reports table in the database
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()

    # Define the SQL query
    sql = '''INSERT INTO reports (user_ID, date_time, lat, lon, description, filename, api_data_temperature, api_data_weather_code)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''

    # Get the current date and time as a string
    current_datetime = str(datetime.now())

    # Execute the query
    cursor.execute(sql, (user_id, current_datetime, lat, lon, characterization, file_path, current_temperature, weather_code))

    # Commit the transaction
    connection.commit()

    # Close the connection
    connection.close()

    # Redirect to the referrer URL
    return redirect(request.referrer)




def validate_parameters(start_date, end_date, data_lat, data_lon, dist, max_reports, sort, return_map):
    # Check for valid parameters
    if data_lat == '' or data_lon == '':
        return "Latitude or longitude cannot be empty"
    if not -90 <= float(data_lat) <= 90 or not -180 <= float(data_lon) <= 180:
        return "Invalid latitude or longitude"
    try:
        dist=int(dist)
        if (dist<0) :
            return "Invalid Distance" 
    except ValueError:
        return "Invalid Distance"
    try:
        max_reports=int(max_reports)
        if (max_reports<0) :
            return "Invalid max_reports" 
    except ValueError:
        return "Invalid max_reports"
    return None

def filter_data(df, start_date, end_date, data_lat, data_lon, dist, max_reports, sort, return_map):
    full_df = df
   
    print('--------------------------------==============================Dates:')
    print(start_date)
    
    # Convert 'date_time' column to datetime objects
    df['date_time'] = pd.to_datetime(df['date_time'])

    # Filter dates
    if start_date and end_date:
        df = df[(df['date_time'] >= start_date) & (df['date_time'] <= end_date)]

    if df.empty:
        return "No data available"

    # Check if data_lat and data_lon are valid latitude and longitude values
    try:
        data_lat = float(data_lat)
        data_lon = float(data_lon)
        if not -90 <= data_lat <= 90 or not -180 <= data_lon <= 180:
            return "Invalid latitude or longitude"
    except ValueError:
        return "Invalid latitude or longitude"

    if df.empty:
        return "No data available"

    # If dist is not provided, assume 0
    if dist is None:
        dist = 0

    # If max_reports is not provided, assume max
    if max_reports is None:
        max_reports = len(df)

    try:
        dist=int(dist)
        if (dist<0) :
            return "Invalid Distance" 
    except ValueError:
        return "Invalid Distance"
    
    if df.empty:
        return "No data available"

    # Filter location
    if(dist==0):
        dist=0
    # Calculate the distance between each report's coordinates and the given coordinates.
    df['distance'] = df.apply(lambda row: geopy.distance.geodesic((row['lat'], row['lon']), (data_lat, data_lon)).km, axis=1)
    # Filter based on the distance
    df = df[df['distance'] <= dist]
    
    if df.empty:
        return "No data available"
    
    # Drop the temporary distance column
    df.drop(columns=['distance'], inplace=True)

    # Determine sorting order
    # Determine sorting order
    sort_asc = sort == 'oldest'

    # Convert 'date_time' column to datetime objects
    df['date_time'] = pd.to_datetime(df['date_time'])

    # Sort DataFrame by 'date_time'
    df.sort_values(by='date_time', ascending=sort_asc, inplace=True)

    # Check if max_reports is a positive integer
    try:
        max_reports=int(max_reports)
        if (max_reports<0) :
            return "Invalid max_reports" 
    except ValueError:
        return "Invalid max_reports"

    # Limit the number of rows if max_reports is provided and greater than 0
    if max_reports > 0:
        df = df.head(max_reports)

    return df

@app.route('/data', methods=['GET'])
def data():
    # Retrieve query parameters
    output_type = request.args.get('outputType')
    # api_key = request.form.get('api_key')
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    data_lat = request.args.get('data_lat')
    data_lon = request.args.get('data_lon')
    dist = request.args.get('dist')
    max_reports = request.args.get('max')
    sort = request.args.get('sort')
    return_map = request.args.get('returnMap')

    # Check for valid parameters
    error_message = validate_parameters(start_date, end_date, data_lat, data_lon, dist, max_reports, sort, return_map)
    if error_message:
        return jsonify({'error': error_message})

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports")
    rows = cursor.fetchall()
    conn.close()

    df = pd.DataFrame(data=rows, columns=[col[0] for col in cursor.description])

    # Filter the DataFrame
    df = filter_data(df, start_date=start_date, end_date=end_date, data_lat=data_lat, data_lon=data_lon,
                     dist=dist, max_reports=max_reports, sort=sort, return_map=return_map)
    print('------------------------------------------------------------------------------------------')
    print(df)
    
    # Check if df is a string
    if isinstance(df, str):
        return 'No data available'

    # Check if df is empty
    if df.empty:
        return 'No data available'
   # Render HTML page if requested
    elif output_type == 'html':
        # Pass the DataFrame data to the HTML template
        # Assuming df is a DataFrame
        data = df.values.tolist()  # Convert DataFrame to list of lists
        return render_template('data.html', data=data)

    # Generate CSV file if requested
    elif output_type == 'csv':
        # Convert DataFrame to CSV string
        csv_string = df.to_csv(index=False)
        # Create a Flask response with the CSV data
        response = make_response(csv_string)
        # Set headers for file download
        response.headers["Content-Disposition"] = "attachment; filename=report_data.csv"
        response.headers["Content-Type"] = "text/csv"
        return response

    # Return JSON text if requested
    elif output_type == 'json':
        return jsonify(df.to_dict(orient='records'))

    # Handle invalid output types
    else:
        return 'Invalid output type'


if __name__ == '__main__':
    app.run(debug=True)
