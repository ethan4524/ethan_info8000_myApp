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



# create app, define folders
app = Flask(__name__, static_folder='static', template_folder='templates')

#weather data dictionary 
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

#create the DataFrame for the weather data
weather_df = pd.DataFrame(weather_data)

#returns the login screen
@app.route('/login')
def login():
    return render_template('login.html')

#redirects the user to the login upon logout
@app.route('/logout')
def logout():
    return redirect('/')

#root: this is also the login 
@app.route('/')
def root():
    return render_template('login.html')

#authenticates the user during login
@app.route('/authenticate', methods=['POST'])
def authenticate():
    #get variables from form 
    username = request.form['username']
    password = request.form['password']

    #connect to database
    con = sqlite3.connect('database.db')

    # Read entire database into a Pandas DataFrame (Is this a security issue? probably... )
    df = pd.read_sql_query("SELECT * FROM userdata", con)

    # Close the database connection
    con.close()

    # Check if the user exists in the DataFrame and password is correct
    user = df[df['username'] == username]
    #validate input and check to see if password hash exists
    if not user.empty and check_password_hash(user.iloc[0]['password'], password):
        # Get the API key for the user
        api_key = user.iloc[0]['api_key']
        # Redirect to user home with username and API key
        print('api_key:' + str(api_key)) #debug stuff
        #redirects to user home
        return redirect(url_for('user_home', username=username, api_key=api_key))
    else:
        # User does not exist or password is incorrect
        return render_template('login.html', error_message="Invalid username or password. Please try again.")

#handles the registration. The user will be sent the user home after succesful registration
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

        return redirect(url_for('user_home', username=username, api_key=api_key))

    return render_template('register.html')

#routes the user home with thier respective username
@app.route('/user_home/<username>')
def user_home(username):
    api_key = request.args.get('api_key')
    return render_template('user_home.html', username=username, api_key=api_key)

# #I'm not using this anymore
# @app.route('/download_data')
# def download_data() :
#     return render_template('/data_query')

# #I'm not using this anymore
# @app.route('/success')
# def success() :
#     return render_template('/data_query')

#function for returning the api key during the report. This is to verify the useris actually signed in and has their key. 
#note: if the user is not, They might see 'welcome, user' and below the api key will be empty
def get_user_id(api_key):
    # Load the database table into a DataFrame
    df = pd.read_sql_query("SELECT * FROM userdata", sqlite3.connect('database.db'))
    
    # Filter the DataFrame to find the user_id associated with the provided API key
    user_id_series = df.loc[df['api_key'] == api_key, 'user_ID']
    
    if not user_id_series.empty:
        return user_id_series.iloc[0]  # Return the user_id if found
    else:
        return None  # Return None if no user_id found for the API key

#this handles reporting new data entries
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
    #stores the file
    file = request.files['file']
    #validates the filename
    if file.filename == '':
        return 'No selected file'

    # Save the file to the srver
    file_path = 'uploads/' + file.filename
    file.save(file_path)

    #Next, using the lat and lon, the current temperature and weather forecast is gathered using API calls from open meteo
    # Make API call to OpenMeteo
    query = f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code'
    response = requests.get(query)
    data = response.json()

    # Parse the JSON response
    current_temperature = data['current']['temperature_2m']
    weather_code = data['current']['weather_code']

    # Interpret weather code (this isn't very important but it is still neat)
    #note: the code is stored on the database - not the description
    weather_description = weather_df.loc[weather_df['Code'] == weather_code, 'Description'].values[0]
    print(weather_description)
    
    #Next, the description is characterized as Normal, offensive, or wildcard using google gemini api call
    # Characterize the Description using Google Gemini
    f = open('./secret_key.txt', 'r')#<------- I am not sure what the best/safest way of doing this is. I'm assuming a hacker could check the local variables and see the key...at least its not hardcoded
    my_key = f.read().strip()  # Use strip() to remove any leading or trailing whitespace
    f.close()
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
        #if the ai is unable to characterize or IF THE API KEY DOES NOT WORK then defualt to this value
        characterization = 'Unable to process characterization'


    # Store data in the reports table in the database
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()

    # Define the SQL query
    sql = '''INSERT INTO reports (user_ID, date_time, lat, lon, description, filename, api_data_temperature, api_data_weather_code)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''

    # Get the current date and time as a string
    current_datetime = str(datetime.now())

    # Execute the query, finalize
    cursor.execute(sql, (user_id, current_datetime, lat, lon, characterization, file_path, current_temperature, weather_code))
    connection.commit()
    connection.close()

    # Redirect to the referrer URL
    return redirect(request.referrer)



#this function checks the inputs to the filter parameters. If the parameters are invalid, they will default to None which will not filter anything for that parameter. 
# this function also maintains a consistant format for the rest of the code by returning the variable in the desired type
def validate_parameters(data_lat, data_lon, dist, max_reports, sort, return_map):
    # Check for valid parameters
    # validate lat,lon
    if not data_lat or not data_lon:
        data_lat = None
        data_lon = None
    else:
        try:
            #make them floats and valid values
            data_lat = float(data_lat)
            data_lon = float(data_lon)
            if not -90 <= data_lat <= 90 or not -180 <= data_lon <= 180:
                data_lat = None
                data_lon = None
        except ValueError:
            data_lat = None
            data_lon = None
    #Validate distance
    try:
        if dist is not None:
            dist = int(dist)
            if dist < 0:
                dist = None
    except ValueError:
        dist = None
    #validate max reports
    try:
        if max_reports is not None:
            max_reports = int(max_reports)
            if max_reports < 0:
                max_reports = None
    except ValueError:
        max_reports = None
    #return values (note: these are updated to the ideal format)
    return data_lat, data_lon, dist, max_reports, sort, return_map

#the following method applies the filteres on the database. I chose to use pandas because I understand it better. Note: if any parameter is left blank, it is handled as None and won't break anything (hopefullt)
def filter_data(df, start_date=None, end_date=None, data_lat=None, data_lon=None, dist=None, max_reports=None, sort='oldest', return_map=None):
    full_df = df
   
    #convert 'date_time' column to datetime objects (this is to better sort)
    df['date_time'] = pd.to_datetime(df['date_time'])

    # Filter dates in the df 
    if start_date:
        start_date = pd.to_datetime(start_date)
        df = df[df['date_time'] >= start_date]    
    if end_date:
        end_date = pd.to_datetime(end_date)
        df = df[df['date_time'] <= end_date]
    # after each filter, the dataframe is examined to see if it is empty. If so, go ahead and return it. 
    if df.empty:
        return "No data available"

    # Check if data_lat and data_lon are valid latitude and longitude values
    if data_lat is not None and data_lon is not None:
        try:
            data_lat = float(data_lat)
            data_lon = float(data_lon)
            if not -90 <= data_lat <= 90 or not -180 <= data_lon <= 180:
                return "Invalid latitude or longitude"
        except ValueError:
            return "Invalid latitude or longitude"
    
    # Filter location if both lat and lon are provided and valid
    if data_lat is not None and data_lon is not None:
        if dist is None:
            dist = 1  # Default distance of 1 km if not provided
        df['distance'] = df.apply(lambda row: geopy.distance.geodesic((row['lat'], row['lon']), (data_lat, data_lon)).km, axis=1)
        df = df[df['distance'] <= dist]
        df.drop(columns=['distance'], inplace=True)

    # Determine sorting order from the form variable (oldest means oldest to newest)
    sort_asc = sort == 'oldest'

    # Sort DataFrame by 'date_time'
    df.sort_values(by='date_time', ascending=sort_asc, inplace=True)

    # Limit the number of rows if max_reports is provided and greater than 0
    if max_reports is not None and max_reports > 0:
        df = df.head(max_reports)
    #return the filtered df
    return df

#This handles the data retrieval and will redirect accordingly
@app.route('/data', methods=['GET'])
def data():
    # Retrieve query parameters from the form
    output_type = request.args.get('outputType')
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    data_lat = request.args.get('data_lat')
    data_lon = request.args.get('data_lon')
    dist = request.args.get('dist')
    max_reports = request.args.get('max')
    sort = request.args.get('sort')
    return_map = request.args.get('returnMap') #not implemented yet... I planned on returning an HTML with an embedded geopandas mapp. 


    # Check for valid parameters, default the values if needed. This also returns them in the correct type 
    data_lat, data_lon, dist, max_reports, sort, return_map = validate_parameters(data_lat, data_lon, dist, max_reports, sort, return_map)

    #open the database, extract the data
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports")
    rows = cursor.fetchall()
    conn.close()
    #convert to pandas df for easier data management
    df = pd.DataFrame(data=rows, columns=[col[0] for col in cursor.description])

    # Filter the df using the filter data function. Returns the filtered dataframe
    df = filter_data(df, start_date=start_date, end_date=end_date, data_lat=data_lat, data_lon=data_lon,
                     dist=dist, max_reports=max_reports, sort=sort, return_map=return_map)
    print(df)
    
    # Check if df is a string -- if the df is a string, then there is no data avalialbe. This was an issue I had for a while.
    if isinstance(df, str):
        return 'No data available'
    
    # Check if df is empty
    if df.empty:
        return 'No data available'
   
    # Render HTML page if requested
    elif output_type == 'html':
        #converts the df to a list of lists. This will be parsed by the HTML form to populate the table. 
        data = df.values.tolist() 
        return render_template('data.html', data=data)

    # Generate CSV file if requested
    elif output_type == 'csv':
        # convert df intto a CSV string
        csv_string = df.to_csv(index=False)
        # Create a Flask response with the CSV data (this is what will be downloaded)
        response = make_response(csv_string)
        # Set headers for file download
        response.headers["Content-Disposition"] = "attachment; filename=report_data.csv"
        response.headers["Content-Type"] = "text/csv"
        return response #downloads the csv with the reports

    # Return JSON text if requested
    elif output_type == 'json':
        return jsonify(df.to_dict(orient='records'))

    # Handle invalid output types (just in case)
    else:
        return 'Invalid output type'

#runs the app
if __name__ == '__main__':
    app.run(debug=True)
