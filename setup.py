from flask import Flask,request,render_template
from werkzeug.utils import secure_filename
import csv
import sqlite3
from flask_cors import CORS
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

with sqlite3.connect("database.db") as con:
    with open("FILE.sql") as f:
        con.executescript(f.read())