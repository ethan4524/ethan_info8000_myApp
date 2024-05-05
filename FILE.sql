-- CREATE TABLE userdata (
--         username type constraints,
--         user_ID type constraints,
--         password type constraints,
--         api_key type constraints
        
-- );

CREATE TABLE reports (
        user_ID type constraints,
        date_time type constraints,
        lat type constraints,
        lon type constraints,
        description type constraints,
        filename type constraints,
        api_data_temperature type constraints,
        api_data_weather_code type constraints
        
);

-- CREATE INDEX index_test ON userdata(username,user_ID,password,api_key)
CREATE INDEX index_test ON reports(user_ID,date_time,lat,lon,description,filename,api_data_temperature,api_data_weather_code)
