import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
os.environ["API_KEY"] = "pk_a3ac73c946c447b4a9912ca07a54a9e6"


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Gets the cash ramining of the current user from database
    user = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cash = user[0]["cash"]

    # Gets the symbol and total shares the user is currently holding from database
    stocks = db.execute(
        "SELECT symbol, SUM(shares) AS total_shares, price FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0", user_id=session["user_id"])

    total = cash
    # Puts the data of lookup in a dictionary
    quotes = {}
    for stock in stocks:
        quotes[stock["symbol"]] = lookup(stock["symbol"])
        diff = quotes[stock["symbol"]]["price"] - stock["price"]
        quotes[stock["symbol"]]["price_difference"] = diff
        if quotes[stock["symbol"]]["price_difference"] > 0:
            quotes[stock["symbol"]]["price_difference"] = "+" + "{:.2f}".format(diff)
        elif quotes[stock["symbol"]]["price_difference"] == 0:
            quotes[stock["symbol"]]["price_difference"] = "-"
        else:
            quotes[stock["symbol"]]["price_difference"] = "{:.2f}".format(diff)
        total += quotes[stock["symbol"]]["price"] * stock["total_shares"]

    return render_template("index.html", cash=cash, stocks=stocks, quotes=quotes, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        code = request.form.get("symbol")
        # Checks whether user input a stock code
        if not code:
            return apology("Please enter a stock code", 400)

        # Check whether stock code is valid
        if lookup(code) == None:
            return apology("Invalid stock code", 400)

        # Checks whether user input a number and whether number is negative or 0
        if not request.form.get("shares") or ((request.form.get("shares")) <= str(0)) or not request.form.get("shares").isnumeric():
            return apology("invalid number of shares to buy", 400)

        num = float(request.form.get("shares"))

        # Checks if number input is an int
        if (num % 1 != 0):
            return apology("shares must be a positive integer", 400)

        number_of_shares = int(request.form.get("shares"))
        quote = lookup(code)
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        price_of_share = quote["price"]
        cash_remaining = rows[0]["cash"]

        total_price = price_of_share * number_of_shares

        # Checks if the user has sufficient funds to buy the stocks
        if total_price > cash_remaining:
            return apology("not enough funds")

        # Updates user's cash left
        db.execute("UPDATE users SET cash = cash - :price WHERE id = :user_id", price=total_price, user_id=session["user_id"])

        # Insert the transaction into database
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES(:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"],
                   symbol=(request.form.get("symbol")).upper(),
                   shares=number_of_shares,
                   price=price_of_share)

        flash("Bought!")

        return redirect("/")

    return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get("username")
    names = db.execute("SELECT * FROM users WHERE username = :username", username=username)
    if username and names:
        return jsonify(False)
    elif not username and names:
        return jsonify(True)
    else:
        return jsonify(True)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transactions = db.execute(
        "SELECT symbol, shares, price, date_time FROM transactions WHERE user_id = :user_id ORDER BY date_time ASC", user_id=session["user_id"])

    return render_template("transactions.html", transactions=transactions)


@app.route("/add_funds", methods=["GET", "POST"])
@login_required
def add_funds():
    """Adds funds to user logged in"""
    if request.method == "POST":
        funds = request.form.get("number")
        if not funds:
            return apology("input amount of funds to add", 400)

        if int(funds) <= 0:
            return apology("funds to add can't be less than 0", 400)

        db.execute("UPDATE users SET cash = cash + :fund WHERE id = :user_id", fund=funds, user_id=session["user_id"])
        flash("Funds added!")
        return redirect("/")

    return render_template("add_funds.html")


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """Changes the user's password"""
    if request.method == "POST":
        # Ensure current password is not empty
        if not request.form.get("old"):
            return apology("must provide current password", 400)

        # Query database for user_id
        rows = db.execute("SELECT hash FROM users WHERE id = :user_id", user_id=session["user_id"])

        # Ensure current password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("old")):
            return apology("invalid password", 400)

        # Ensure new password is not empty
        if not request.form.get("new"):
            return apology("must provide new password", 400)

        # Ensure new password confirmation is not empty
        elif not request.form.get("confirm"):
            return apology("must provide new password confirmation", 400)

        # Ensure new password and confirmation match
        elif request.form.get("new") != request.form.get("confirm"):
            return apology("new password and confirmation must match", 400)

        # Update database
        hashed = generate_password_hash(request.form.get("new"))
        rows = db.execute("UPDATE users SET hash = :hash WHERE id = :user_id", user_id=session["user_id"], hash=hashed)

        # Show flash
        flash("Changed!")

        return redirect("/")

    return render_template("change_password.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Checks whether user imput stock code
        if not request.form.get("symbol"):
            return apology("Please type in a symbol", 400)

        # Handles multiple inputs from user if user wants to check quotes of multiple stocks
        lst = [x.strip() for x in request.form.get("symbol").split(",")]
        quotes = []
        for i in lst:
            check = lookup(i)
            print(check)
            # Checks whether user stock code is valid
            if check == None:
                return apology("invalid symbol", 400)
            quotes.append(check)

        return render_template("quoted.html", quotes=quotes)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        password = request.form.get("password")
        confirm = request.form.get("confirmation")
        username = request.form.get("username")

        # Ensures that a username was submitted
        if not username:
            return apology("must enter username", 400)

        # Ensures that password was submitted
        elif not password:
            return apology("must enter password", 400)

        # Ensures that confimation was submitted
        elif not confirm:
            return apology("must enter confirmation", 400)

        # Ensures that confimation was submitted
        elif confirm != password:
            return apology("Passwords do not match", 400)

        else:
            # Hashes the users password
            hashed = generate_password_hash(password)
            # Inserts username and password hash into database
            new_user = db.execute("INSERT INTO users(username,hash) VALUES(:username, :hashed)", username=username, hashed=hashed)
            # Checks whether username was already taken
            if not new_user:
                return apology("Username already taken", 400)
            # Stores the session id as the user
            session["user_id"] = new_user
            flash("Registered!")
            return redirect("/login")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    symbols = db.execute(
        "SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0", user_id=session["user_id"])
    if request.method == "POST":
        symbol = request.form.get("symbol")
        num = float(request.form.get("shares"))

        # Checks whether user input symbol
        if not symbol:
            return apology("Enter symbol", 400)

        quote = lookup(symbol)

        # Check if the symbol exists
        if quote == None:
            return apology("invalid symbol", 400)

        # Checks if number input is an int
        if (num % 1 != 0):
            return apology("shares must be a positive integer", 400)

        # Check if # of shares requested was 0
        if num <= 0:
            return apology("can't sell less 0 or less shares", 400)

        # Check if we have enough shares
        stock = db.execute("SELECT SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol",
                           user_id=session["user_id"], symbol=request.form.get("symbol"))

        if len(stock) != 1 or stock[0]["total_shares"] <= 0 or stock[0]["total_shares"] < num:
            return apology("you can't sell more than you own", 400)

        price = quote["price"]

        # Calculate the price of requested shares
        total_price = price * num

        # Updates users cash in database
        db.execute("UPDATE users SET cash = cash + :price WHERE id = :user_id", price=total_price, user_id=session["user_id"])

        # Logs the transaction into database
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES(:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"],
                   symbol=request.form.get("symbol"),
                   shares=-num,
                   price=price)

        flash("Sold!")
        return redirect("/")

    return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)