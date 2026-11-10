
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from io import BytesIO

from database import init_db, get_db_connection
from gnani.stt import GnaniSTTClient
from gnani.tts import GnaniTTSClient

import os
import re
import json
import tempfile
import requests
import time
from dotenv import load_dotenv

load_dotenv()

GNANI_API_KEY = os.getenv("GNANI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dukaansaathi-local-secret")

print("Gnani API Key Loaded:", bool(GNANI_API_KEY))

stt_client = GnaniSTTClient(api_key=GNANI_API_KEY)
tts_client = GnaniTTSClient(api_key=GNANI_API_KEY)

init_db()


def understand_sale_command(transcript, products):
    """Use Gemini to map a Telugu/English command to a safe sale draft."""
    if not GEMINI_API_KEY:
        return None

    product_list = [
        {"name": product["name"], "unit": product["unit"]}
        for product in products
    ]
    prompt = (
        "Interpret this shopkeeper voice transcript. Only extract a sale request; "
        "do not invent missing details. Match product_name to one of the supplied "
        "inventory names, preserving its exact spelling. If this is not clearly a "
        "sale command or a required detail is missing, use an empty string for text "
        "fields and 0 for quantity. Respond only with JSON having keys action "
        "(sale or unclear), product_name (string), quantity (number), unit (string), "
        "customer_name (string).\n"
        f"Inventory: {json.dumps(product_list, ensure_ascii=False)}\n"
        f"Transcript: {transcript}"
    )
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["sale", "unclear"]},
            "product_name": {"type": "string"},
            "quantity": {"type": "number"},
            "unit": {"type": "string"},
            "customer_name": {"type": "string"},
        },
        "required": ["action", "product_name", "quantity", "unit", "customer_name"],
    }
    response = None
    for attempt in range(3):
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": GEMINI_API_KEY},
            json={
                "model": GEMINI_MODEL,
                "input": prompt,
                "response_format": {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema,
                },
            },
            timeout=30,
        )
        if response.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
            break
        time.sleep(1.5 * (2 ** attempt))

    if not response.ok:
        try:
            error_message = response.json().get("error", {}).get("message", "Unknown Gemini API error")
        except ValueError:
            error_message = "Gemini returned a non-JSON error response"
        raise RuntimeError(f"Gemini API returned HTTP {response.status_code}: {error_message}")
    data = response.json()
    interaction = data.get("interaction", data)
    output_text = interaction.get("output_text")
    if not output_text:
        raise ValueError("Gemini returned no command result")
    return json.loads(output_text)





import re

def extract_sale_details(transcript):
    text = transcript.lower().strip()

    # Telugu and English number words
    number_words = {
        "ఒకటి": 1, "ఒక": 1, "వన్": 1, "one": 1,
        "రెండు": 2, "రెండూ": 2, "రెండు కిలో": 2, "రెండు కేజీ": 2, "టూ": 2, "two": 2,
        "మూడు": 3, "త్రీ": 3, "three": 3,
        "నాలుగు": 4, "ఫోర్": 4, "four": 4,
        "ఐదు": 5, "ఫైవ్": 5, "five": 5,
        "ఆరు": 6, "సిక్స్": 6, "six": 6,
        "ఏడు": 7, "సెవెన్": 7, "seven": 7,
        "ఎనిమిది": 8, "ఎయిట్": 8, "eight": 8,
        "తొమ్మిది": 9, "నైన్": 9, "nine": 9,
        "పది": 10, "టెన్": 10, "ten": 10,
        "ట్వంటీ": 20, "ట్వెంటీ": 20, "ట్వెంటీ": 20, "ఇరవై": 20,
        "twenty": 20,
    }

    # Common spoken Telugu rendered in Latin script by speech recognition.
    transliterated_numbers = {
        "okati": 1, "oka": 1, "rendu": 2, "rendu": 2, "moodu": 3,
        "nalugu": 4, "aidu": 5, "aido": 5, "aaru": 6, "edu": 7,
        "enimidi": 8, "tommidi": 9, "padi": 10,
    }
    number_words.update(transliterated_numbers)

    # Identify quantity
    quantity = None

    numeric_match = re.search(r'(\d+(?:\.\d+)?)', text)

    if numeric_match:
        quantity = float(numeric_match.group(1))
    else:
        number_pattern = "|".join(re.escape(word) for word in sorted(number_words, key=len, reverse=True))
        verbal_quantity = re.search(
            rf"({number_pattern})\s*(?:కిలోలు?|కేజీలు?|కేజీ|kg|grams?|గ్రాములు?|లీటర్లు?|లీటర్|pieces?|పీసులు?|packets?|ప్యాకెట్లు?)",
            text,
        )
        if verbal_quantity:
            quantity = float(number_words[verbal_quantity.group(1)])
        else:
            for word, value in sorted(number_words.items(), key=lambda item: len(item[0]), reverse=True):
                if word in text:
                    quantity = float(value)
                    break

    # Identify unit
    unit = None

    unit_aliases = {
        "kg": ["kg", "కేజీ", "కేజెస్", "కేజీలు", "కిలో", "కిలోలు"],
        "g": ["grams", "gram", "గ్రాములు", "గ్రాము"],
        "litre": ["litres", "litre", "లీటర్లు", "లీటర్"],
        "ml": ["ml", "మిల్లీలీటర్లు", "మిల్లీ"],
        "piece": ["pieces", "piece", "పీసులు", "పీస్"],
        "packet": ["packets", "packet", "ప్యాకెట్లు", "ప్యాకెట్"]
    }

    for standard_unit, aliases in unit_aliases.items():
        if any(alias in text for alias in aliases):
            unit = standard_unit
            break

    # Identify product
    product_name = None

    product_words = {
        "షుగర్": "sugar",
        "సుగర్": "sugar",
        "sugar": "sugar",
        "రైస్": "rice",
        "బియ్యం": "rice",
        "rice": "rice",
        "పప్పు": "pappu",
        "పప్పు": "pappu",
        "pappu": "pappu",
        "dal": "pappu",
        "ఆయిల్": "oil",
        "నూనె": "oil",
        "oil": "oil",
        "పప్పు": "pappu",
        "pappu": "pappu",
        "dal": "pappu",
        "రవ్వ": "ravva",
        "సెమోలినా": "ravva"
    }

    for word, name in product_words.items():
        if word in text:
            product_name = name
            break

    # Identify customer name
    customer_name = None

    customer_match = re.search(r'^(.+?)(?:\s*కి|\s+ki\b)', text)

    if customer_match:
        customer_name = customer_match.group(1).strip()

    return {
        "customer_name": customer_name,
        "product_name": product_name,
        "quantity": quantity,
        "unit": unit
    }


def extract_product_details(transcript):
    """Extract fields for a spoken add-product request."""
    text = transcript.strip()
    normalized = text.casefold()

    action_markers = (
        "add product", "new product", "add item", "new item",
        "add to inventory", "add in inventory", "stock lo add",
        "inventory lo add", "product add", "product add chey",
        "add stock item", "kotha product", "kotha item",
        "ప్రొడక్ట్ యాడ్", "కొత్త ప్రొడక్ట్", "కొత్త వస్తువు", "కొత్త ఐటమ్",
        "జోడించు", "చేర్చు", "యాడ్ చేయి", "యాడ్ చెయ్యి", "స్టాక్ పెట్టు",
        "స్టాక్‌లో చేర్చు", "కొత్తగా చేర్చు", "కొనిన సరుకు", "సరుకు చేర్చు",
    )
    if not any(marker in normalized for marker in action_markers):
        return None

    unit_aliases = {
        "kg": ("కిలోలు", "కిలో", "కేజీలు", "కేజీ", "kg", "kilos", "kilo"),
        "g": ("గ్రాములు", "గ్రాము", "grams", "gram", " g "),
        "litre": ("లీటర్లు", "లీటర్", "litres", "litre", "liter", "liters"),
        "ml": ("మిల్లీలీటర్లు", "మిల్లీలీటర్", "ml"),
        "piece": ("పీసులు", "పీస్", "pieces", "piece"),
        "packet": ("ప్యాకెట్లు", "ప్యాకెట్", "packets", "packet"),
    }
    unit = None
    matched_unit = None
    for standard, aliases in unit_aliases.items():
        for alias in aliases:
            if alias.strip() in normalized:
                unit = standard
                matched_unit = alias.strip()
                break
        if unit:
            break

    number_words = {
        "ఒకటి": 1, "ఒక": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4,
        "ఐదు": 5, "ఆరు": 6, "ఏడు": 7, "ఎనిమిది": 8, "తొమ్మిది": 9,
        "పది": 10, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "oka": 1, "okati": 1, "rendu": 2, "moodu": 3,
        "nalugu": 4, "aidu": 5, "aaru": 6, "edu": 7, "enimidi": 8,
        "tommidi": 9, "padi": 10, "ట్వంటీ": 20, "ట్వెంటీ": 20,
        "twenty": 20, "ఇరవై": 20,
    }

    values = re.findall(r"\d+(?:\.\d+)?", normalized)
    quantity = float(values[0]) if values else None
    if quantity is None:
        for word in sorted(number_words, key=len, reverse=True):
            if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", normalized) or word in normalized:
                quantity = float(number_words[word])
                break

    price_patterns = (
        r"(?:ధర|రేటు|price|rate)\s*(?:రూ?\.?\s*)?(\d+(?:\.\d+)?)",
        r"(?:రూ\.?|₹)\s*(\d+(?:\.\d+)?)",
    )
    price = None
    for pattern in price_patterns:
        match = re.search(pattern, normalized)
        if match:
            price = float(match.group(1))
            break
    if price is None:
        prices = re.findall(r"\d+(?:\.\d+)?", normalized)
        if len(prices) >= 2:
            price = float(prices[1])

    # Remove numeric and price fields first, then whole action/unit tokens.
    # This avoids stripping text inside valid product names.
    name = re.sub(r"\b(?:rupees?|rs\.?|రూపాయలు?)\b", " ", text, flags=re.IGNORECASE)
    for pattern in price_patterns:
        name = re.sub(pattern, " ", name, flags=re.IGNORECASE)
    name = re.sub(r"\d+(?:\.\d+)?|[₹]|రూ\.?", " ", name, flags=re.IGNORECASE)
    for marker in sorted(action_markers, key=len, reverse=True):
        name = re.sub(re.escape(marker), " ", name, flags=re.IGNORECASE)
    for aliases in unit_aliases.values():
        for alias in sorted(aliases, key=len, reverse=True):
            name = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", " ", name, flags=re.IGNORECASE)
    name = re.sub(r"ధర|రేటు|price|rate|stock|స్టాక్|వస్తువు|ప్రొడక్ట్|product", " ", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip(" .,:;- ")

    return {"name": name, "quantity": quantity, "unit": unit, "price": price}


@app.route("/")
def dashboard():
    conn = get_db_connection()

    products = conn.execute(
        "SELECT * FROM products WHERE active = 1 ORDER BY id DESC"
    ).fetchall()

    total_products = conn.execute(
        "SELECT COUNT(*) FROM products WHERE active = 1"
    ).fetchone()[0]

    total_sales = conn.execute(
        "SELECT COALESCE(SUM(total), 0) FROM sales"
    ).fetchone()[0]

    low_stock = conn.execute(
        "SELECT COUNT(*) FROM products WHERE active = 1 AND stock <= 5"
    ).fetchone()[0]

    archived_products = conn.execute(
        "SELECT id, name FROM products WHERE active = 0 ORDER BY id DESC"
    ).fetchall()

    recent_sales = conn.execute(
        """SELECT sales.id, sales.customer_name, sales.quantity, sales.unit,
                  sales.unit_price, sales.total, sales.sale_date,
                  products.name AS product_name
           FROM sales LEFT JOIN products ON products.id = sales.product_id
           ORDER BY sales.id DESC LIMIT 10"""
    ).fetchall()

    conn.close()

    return render_template(
        "index.html",
        products=products,
        total_products=total_products,
        total_sales=total_sales,
        low_stock=low_stock,
        archived_products=archived_products,
        recent_sales=recent_sales,
        pending_sale=session.get("pending_sale"),
        pending_product=session.get("pending_product")
    )


@app.route("/add_product", methods=["POST"])
def add_product():
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "kg").strip()

    try:
        price = float(request.form.get("price", 0))
        stock = float(request.form.get("stock", 0))
    except (ValueError, TypeError):
        flash("Please enter valid price and stock.")
        return redirect(url_for("dashboard"))

    if not name or price <= 0 or stock < 0:
        flash("Please enter valid product details.")
        return redirect(url_for("dashboard"))

    if unit not in {"kg", "g", "litre", "ml", "piece", "packet"}:
        flash("Please select a valid product unit.")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    duplicate = conn.execute(
        "SELECT id FROM products WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    conn.close()
    if duplicate:
        flash("A product with this name already exists.")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()

    conn.execute(
        """INSERT INTO products (name, price, stock, unit)
           VALUES (?, ?, ?, ?)""",
        (name, price, stock, unit)
    )

    conn.commit()
    conn.close()

    flash("Product added successfully!")
    return redirect(url_for("dashboard"))
@app.route("/delete_product/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    conn = get_db_connection()

    product = conn.execute(
        "SELECT id FROM products WHERE id = ? AND active = 1", (product_id,)
    ).fetchone()
    if product is None:
        conn.close()
        flash("Product not found in active inventory.")
        return redirect(url_for("dashboard"))

    # Preserve sales history by archiving products that have been sold.
    sale = conn.execute(
        "SELECT id FROM sales WHERE product_id = ? LIMIT 1",
        (product_id,)
    ).fetchone()

    if sale:
        conn.execute("UPDATE products SET active = 0 WHERE id = ?", (product_id,))
        conn.commit()
        conn.close()
        flash("Product removed from active inventory. Past sales were kept.")
        return redirect(url_for("dashboard"))

    # Delete product if no sales history exists
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))

    conn.commit()
    conn.close()

    flash("Product deleted successfully!")
    return redirect(url_for("dashboard"))


@app.route("/restore_product/<int:product_id>", methods=["POST"])
def restore_product(product_id):
    conn = get_db_connection()
    result = conn.execute(
        "UPDATE products SET active = 1 WHERE id = ? AND active = 0",
        (product_id,),
    )
    conn.commit()
    conn.close()

    if result.rowcount:
        flash("Product restored to active inventory.")
    else:
        flash("Archived product not found.")
    return redirect(url_for("dashboard"))


@app.route("/confirm_voice_product", methods=["POST"])
def confirm_voice_product():
    pending = session.get("pending_product")
    if not pending:
        flash("No pending voice product found.")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    duplicate = conn.execute(
        "SELECT id FROM products WHERE LOWER(name) = LOWER(?)", (pending["name"],)
    ).fetchone()
    if duplicate:
        conn.close()
        session.pop("pending_product", None)
        flash("A product with this name already exists.")
        return redirect(url_for("dashboard"))

    conn.execute(
        "INSERT INTO products (name, price, stock, unit) VALUES (?, ?, ?, ?)",
        (pending["name"], pending["price"], pending["quantity"], pending["unit"]),
    )
    conn.commit()
    conn.close()
    session.pop("pending_product", None)
    flash(f"{pending['name']} added to inventory successfully.")
    return redirect(url_for("dashboard"))


@app.route("/cancel_voice_product", methods=["POST"])
def cancel_voice_product():
    session.pop("pending_product", None)
    flash("Voice product addition cancelled. Inventory was not changed.")
    return redirect(url_for("dashboard"))


@app.route("/sell_product", methods=["POST"])
def sell_product():
    customer_name = request.form.get("customer_name", "").strip()

    try:
        product_id = int(request.form.get("product_id"))
        quantity = float(request.form.get("quantity"))
    except (ValueError, TypeError):
        flash("Please select a product and enter a valid quantity.")
        return redirect(url_for("dashboard"))

    if quantity <= 0:
        flash("Quantity must be greater than zero.")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()

    try:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()

        if product is None:
            flash("Product not found.")

        elif product["stock"] < quantity:
            flash("Not enough stock available.")

        else:
            unit_price = product["price"]
            unit = product["unit"]
            total = unit_price * quantity

            update_result = conn.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                (quantity, product_id, quantity)
            )
            if update_result.rowcount != 1:
                conn.rollback()
                flash("Stock changed. Please refresh and try again.")
                return redirect(url_for("dashboard"))

            conn.execute(
                """INSERT INTO sales
                (product_id, customer_name, quantity, unit_price, total, unit)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (product_id, customer_name, quantity,
                 unit_price, total, unit)
            )

            conn.commit()
            flash(f"Sale recorded! Total: Rs. {total:.2f}")

    except Exception:
        conn.rollback()
        flash("Unable to record sale. Please try again.")
        raise

    finally:
        conn.close()

    return redirect(url_for("dashboard"))


@app.route("/transcribe", methods=["POST"])
def transcribe_audio():

    if "audio" not in request.files:
        flash("Please record your voice first.")
        return redirect(url_for("dashboard"))

    audio = request.files["audio"]

    if audio.filename == "":
        flash("No audio selected.")
        return redirect(url_for("dashboard"))

    temp_path = None

    try:
        # Save uploaded audio as a temporary WAV file
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False
        ) as temp_audio:
            temp_path = temp_audio.name

        audio.save(temp_path)

        # Send WAV file path to Gnani STT
        result = stt_client.transcribe(
            temp_path,
            language_code="te-IN",
            model="prisma-v3.0",
            keywords=["sugar", "rice", "oil", "ravva"],
            topic="Telugu shop inventory and sales commands",
        )

        transcript = result.get("transcript", "")

        if transcript:
            print("Recognized Voice:", transcript)

            product_details = extract_product_details(transcript)
            if product_details is not None:
                name = product_details["name"]
                quantity = product_details["quantity"]
                price = product_details["price"]
                unit = product_details["unit"]
                if not name or quantity is None or price is None or not unit:
                    flash(
                        "Product details unclear. Say product name, opening stock with unit, "
                        "and price per unit; for example: add product soap, 10 pieces, "
                        "price 25 rupees."
                    )
                    return redirect(url_for("dashboard"))
                if quantity <= 0 or price <= 0:
                    flash("Opening stock and unit price must be greater than zero.")
                    return redirect(url_for("dashboard"))

                conn = get_db_connection()
                existing = conn.execute(
                    "SELECT id FROM products WHERE LOWER(name) = LOWER(?)", (name,)
                ).fetchone()
                conn.close()
                if existing:
                    flash(f"{name} already exists. Use the product form to adjust its stock.")
                    return redirect(url_for("dashboard"))

                session["pending_product"] = {
                    "transcript": transcript,
                    "name": name,
                    "quantity": quantity,
                    "unit": unit,
                    "price": price,
                }
                session.pop("pending_sale", None)
                flash("Please review and confirm the new product details.")
                return redirect(url_for("dashboard"))

            conn = get_db_connection()
            products = conn.execute("SELECT * FROM products").fetchall()
            conn.close()

            try:
                details = understand_sale_command(transcript, products)
            except Exception as e:
                print("LLM Error; using local parser:", repr(e))
                details = None

            if not details or details.get("action") != "sale" or not details.get("product_name") or details.get("quantity") is None:
                details = extract_sale_details(transcript)
                # Resolve known inventory names and aliases to actual products.
                transcript_lower = transcript.casefold()
                for inventory_product in products:
                    inventory_name = inventory_product["name"]
                    if inventory_name.casefold() in transcript_lower:
                        details["product_name"] = inventory_name
                        break
                if not details.get("product_name"):
                    aliases = {
                        "pappu": ("పప్పు", "dal", "పప్పు పప్పు"),
                        "rice": ("బియ్యం", "రైస్"),
                        "sugar": ("షుగర్", "సుగర్", "చక్కెర"),
                        "oil": ("నూనె", "ఆయిల్"),
                        "ravva": ("రవ్వ", "సెమోలినా"),
                    }
                    normalized_transcript = transcript.casefold()
                    for inventory_product in products:
                        canonical = inventory_product["name"].casefold()
                        spoken_aliases = aliases.get(canonical, (canonical,))
                        if any(alias.casefold() in normalized_transcript for alias in spoken_aliases):
                            details["product_name"] = inventory_product["name"]
                            break

            print("Extracted Sale Details:", details)

            customer_name = details["customer_name"]
            product_name = details["product_name"]
            quantity = details["quantity"]

            if details.get("action") not in (None, "sale") or not product_name or quantity is None:
                flash(
                    "Voice recognized, but product or quantity "
                    "was not clearly identified as a sale. Please try again."
                )
                return redirect(url_for("dashboard"))

            if quantity <= 0:
                flash("Please speak a valid quantity.")
                return redirect(url_for("dashboard"))

            conn = get_db_connection()
            try:
                product = next(
                    (p for p in conn.execute("SELECT * FROM products").fetchall()
                     if p["name"].casefold() == str(product_name).strip().casefold()),
                    None,
                )

                if product is None:
                    flash(
                        f"{product_name} is not available in your inventory. "
                        "Please add the product first."
                    )
                    return redirect(url_for("dashboard"))

                if product["stock"] < quantity:
                    flash(
                        f"Not enough stock. Available stock: "
                        f"{product['stock']} {product['unit']}"
                    )
                    return redirect(url_for("dashboard"))

                requested_unit = details.get("unit")
                unit_aliases = {
                    "kg": {"kg", "కిలో", "కిలోలు", "కేజీ", "కేజీలు", "kilo", "kilos"},
                    "g": {"g", "గ్రాము", "గ్రాములు", "gram", "grams"},
                    "litre": {"litre", "litres", "లీటర్", "లీటర్లు"},
                    "ml": {"ml", "మిల్లీ", "మిల్లీలీటర్", "మిల్లీలీటర్లు"},
                    "piece": {"piece", "pieces", "పీస్", "పీసులు"},
                    "packet": {"packet", "packets", "ప్యాకెట్", "ప్యాకెట్లు"},
                }
                normalized_requested_unit = next(
                    (standard for standard, aliases in unit_aliases.items()
                     if requested_unit and requested_unit.casefold() in aliases),
                    requested_unit.casefold() if requested_unit else None,
                )
                if normalized_requested_unit and normalized_requested_unit != product["unit"].casefold():
                    flash(
                        f"You said {requested_unit}, but {product['name']} is tracked in "
                        f"{product['unit']}. Please use matching units."
                    )
                    return redirect(url_for("dashboard"))

                unit_price = product["price"]
                unit = product["unit"]
                total = unit_price * quantity

                # Store pending sale in session.
                # Database will NOT be updated here.
                session["pending_sale"] = {
                    "transcript": transcript,
                    "customer_name": customer_name or "Not provided",
                    "product_name": product["name"],
                    "product_id": product["id"],
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                    "total": total
                }

                flash("Please review the voice sale and confirm it.")

            finally:
                conn.close()

        else:
            flash("No speech detected. Please try again.")

    except Exception as e:
        print("STT Error:", repr(e))
        flash("Voice processing failed. Please try again.")

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    return redirect(url_for("dashboard"))


# Confirm Voice Sale
@app.route("/confirm_voice_sale", methods=["POST"])
def confirm_voice_sale():

    pending_sale = session.get("pending_sale")

    if not pending_sale:
        flash("No pending voice sale found.")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()

    try:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?",
            (pending_sale["product_id"],)
        ).fetchone()

        if product is None:
            flash("Product no longer exists. Sale was not recorded.")
            session.pop("pending_sale", None)
            return redirect(url_for("dashboard"))

        quantity = float(pending_sale["quantity"])

        # Recheck stock before saving
        if product["stock"] < quantity:
            flash(
                f"Not enough stock available. Current stock: "
                f"{product['stock']} {product['unit']}. "
                "Sale was not recorded."
            )
            session.pop("pending_sale", None)
            return redirect(url_for("dashboard"))

        # Use current database price
        unit_price = product["price"]
        unit = product["unit"]
        total = unit_price * quantity

        # Reduce stock only after confirmation
        update_result = conn.execute(
            """UPDATE products
               SET stock = stock - ?
               WHERE id = ? AND stock >= ?""",
            (quantity, product["id"], quantity)
        )

        if update_result.rowcount != 1:
            conn.rollback()
            flash("Stock changed. Please try the sale again.")
            session.pop("pending_sale", None)
            return redirect(url_for("dashboard"))

        # Save confirmed sale
        conn.execute(
            """INSERT INTO sales
               (product_id, customer_name, quantity, unit_price, total, unit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                product["id"],
                pending_sale["customer_name"],
                quantity,
                unit_price,
                total,
                unit
            )
        )

        conn.commit()

        session.pop("pending_sale", None)

        flash(
            f"Voice sale confirmed successfully! "
            f"Total amount: Rs. {total:.2f}"
        )

    except Exception as e:
        conn.rollback()
        print("Voice Sale Confirmation Error:", repr(e))
        flash("Unable to confirm sale. Please try again.")

    finally:
        conn.close()

    return redirect(url_for("dashboard"))


# Cancel Voice Sale
@app.route("/cancel_voice_sale", methods=["POST"])
def cancel_voice_sale():

    session.pop("pending_sale", None)

    flash("Voice sale cancelled. No changes were made to inventory.")

    return redirect(url_for("dashboard"))


@app.route("/speak", methods=["POST"])
def speak_text():
    text = request.form.get("text", "").strip()

    if not text:
        flash("Please enter text for voice response.")
        return redirect(url_for("dashboard"))

    try:
        audio = tts_client.synthesize(
            text,
            voice="Shivani",
            model="timbre-v3.0",
            language="te-IN"
        )

        return send_file(
            BytesIO(audio),
            mimetype="audio/wav",
            as_attachment=False,
            download_name="dukaansaathi_response.wav"
        )

    except Exception as e:
        print("TTS Error:", repr(e))
        flash("Voice generation failed. Please try again.")
        return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
