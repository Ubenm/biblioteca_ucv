from flask import Flask, request, jsonify, render_template, send_from_directory
import mysql.connector
import os
import datetime
from werkzeug.utils import secure_filename
import traceback  # Añadir al inicio del archivo

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        user=os.environ.get("DATABASE_USER", "user"),
        password=os.environ.get("DATABASE_PASSWORD", "password"),
        database=os.environ.get("DATABASE_NAME", "docmanager")
    )

# Inicialización de la base de datos con nuevas tablas
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabla de reuniones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            fecha DATETIME NOT NULL,
            tema VARCHAR(255) NOT NULL,
            participantes TEXT NOT NULL
        );
    ''')
    
    # Tabla de documentos (con soporte para documentos complementarios)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            meeting_id INT NOT NULL,
            tipo ENUM('acta', 'minuta', 'anexo', 'otro') NOT NULL,
            nombre VARCHAR(255) NOT NULL,
            ruta VARCHAR(255) NOT NULL,
            fecha_subida DATETIME NOT NULL,
            parent_id INT,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_id) REFERENCES documents(id) ON DELETE SET NULL
        );
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

@app.before_first_request
def startup():
    init_db()

# ------------------- Gestión de Reuniones -------------------
# Endpoint GET para listar reuniones (NUEVO)

@app.route('/meetings', methods=['GET'])
def get_meetings():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM meetings ORDER BY fecha DESC")
    meetings = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(meetings), 200

# Endpoint POST para crear reuniones (CORREGIDO)
@app.route('/meetings', methods=['POST'])
def create_meeting():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Datos JSON requeridos"}), 400

        # Convertir fecha ISO a datetime
        fecha = datetime.datetime.fromisoformat(data['fecha'].replace('Z', '+00:00'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO meetings (fecha, tema, participantes) VALUES (%s, %s, %s)",
            (fecha, data['tema'], data['participantes'])
        )
        conn.commit()
        meeting_id = cursor.lastrowid
        return jsonify({
            "message": "Reunión creada",
            "meeting_id": meeting_id,
            "fecha": fecha.isoformat()
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
# ------------------- Carga de Documentos -------------------
@app.route('/upload', methods=['POST'])
def upload_document():
    try:
        # Validar campos requeridos
        meeting_id = request.form.get("meeting_id")
        tipo = request.form.get("tipo")
        file = request.files.get("document")

        if not all([meeting_id, tipo, file]):
            return jsonify({"error": "Faltan campos requeridos"}), 400

        # Validar reunión
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM meetings WHERE id = %s", (meeting_id,))
        if not cursor.fetchone():
            return jsonify({"error": "ID de reunión inválido"}), 400

        # Validar documento padre
        parent_id = request.form.get("parent_id")
        if parent_id:
            cursor.execute("SELECT id FROM documents WHERE id = %s AND meeting_id = %s", (parent_id, meeting_id))
            if not cursor.fetchone():
                return jsonify({"error": "Documento principal no válido"}), 400

        # Guardar archivo
        filename = secure_filename(file.filename)  # Usar secure_filename
        unique_name = f"{datetime.datetime.now().timestamp()}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file.save(filepath)

        # Insertar en BD
        cursor.execute("""
            INSERT INTO documents 
            (meeting_id, tipo, nombre, ruta, fecha_subida, parent_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            meeting_id,
            tipo,
            filename,  # Guardar nombre original seguro
            filepath,
            datetime.datetime.now(),
            parent_id if parent_id else None
        ))
        conn.commit()

        return jsonify({
            "message": "Documento subido",
            "document_id": cursor.lastrowid,
            "filename": filename
        }), 201

    except Exception as e:
        return jsonify({"error": f"Error interno: {str(e)}"}), 500
    finally:
        cursor.close()
        conn.close()
# ------------------- Índice de Reuniones -------------------
@app.route('/meetings/<int:meeting_id>/index')
def meeting_index(meeting_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Obtener documentos principales y sus anexos
    cursor.execute('''
        SELECT d.*, m.fecha, m.tema 
        FROM documents d
        JOIN meetings m ON d.meeting_id = m.id
        WHERE d.meeting_id = %s
        ORDER BY d.parent_id IS NULL DESC, d.fecha_subida
    ''', (meeting_id,))
    
    documents = cursor.fetchall()
    organized = {}
    for doc in documents:
        if doc['parent_id'] is None:
            organized[doc['id']] = {**doc, 'anexos': []}
        else:
            organized[doc['parent_id']]['anexos'].append(doc)
    
    cursor.close()
    conn.close()
    return jsonify(list(organized.values()))

# ------------------- Búsqueda Avanzada -------------------
@app.route('/search')
def search_documents():
    params = request.args
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        query = '''
            SELECT d.*, m.fecha, m.tema 
            FROM documents d
            JOIN meetings m ON d.meeting_id = m.id
            WHERE 1=1
        '''
        filters = []
        values = []
        
        # Filtro por palabra clave (solo si no está vacío)
        keyword = params.get('keyword', '').strip()
        if keyword:
            filters.append("(d.nombre LIKE %s OR m.tema LIKE %s OR m.participantes LIKE %s)")
            values.extend([f"%{keyword}%"] * 3)
        
        # Filtro por tipo (solo si se selecciona)
        tipo = params.get('tipo', '')
        if tipo:
            filters.append("d.tipo = %s")
            values.append(tipo)
        
        # Filtro por fecha (solo si es válida)
        fecha = params.get('fecha', '')
        if fecha:
            try:
                datetime.datetime.strptime(fecha, "%Y-%m-%d")
                filters.append("DATE(m.fecha) = %s")
                values.append(fecha)
            except ValueError:
                return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400
        
        # Construir consulta final
        if filters:
            query += " AND " + " AND ".join(filters)
        
        cursor.execute(query, values)
        results = cursor.fetchall()
        return jsonify(results), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# ------------------- Descarga/Visualización -------------------
@app.route('/documents/<int:doc_id>')
def get_document(doc_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT ruta, nombre FROM documents WHERE id = %s", (doc_id,))
    doc = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not doc:
        return jsonify({"error": "Documento no encontrado"}), 404
    
    # Verificar tipo de archivo para visualización
    if doc['nombre'].lower().endswith(('.txt', '.pdf')):
        return send_from_directory(os.path.dirname(doc['ruta']), os.path.basename(doc['ruta']))
    else:
        return send_from_directory(os.path.dirname(doc['ruta']), os.path.basename(doc['ruta']), as_attachment=True)

# ------------------- Frontend -------------------
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)