from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
import pymysql
from datetime import datetime, timedelta
import os
from fpdf import FPDF
import jwt
from functools import wraps

app = Flask(__name__)
CORS(app)

# Configuración JWT
app.config['SECRET_KEY'] = 'licoreria_secret_key_2025'
app.config['JWT_EXPIRATION_DELTA'] = timedelta(hours=8)

# Verificar JWT
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
            
        if not token:
            return jsonify({'message': 'Token no proporcionado!', 'success': False}), 401
            
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            g.current_user = data['user']
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expirado!', 'success': False}), 401
        except Exception as e:
            print(f"Error decodificando token: {e}")
            return jsonify({'message': 'Token inválido!', 'success': False}), 401
            
        return f(*args, **kwargs)
    return decorated

# Verificar rol de admin
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if g.current_user['rol'] != 'admin':
            return jsonify({'message': 'Acceso solo para administradores!', 'success': False}), 403
        return f(*args, **kwargs)
    return decorated

# Conexión a la base de datos
def conectar():
    return pymysql.connect(
        host='localhost',
        user='root',
        passwd='',
        db='sistema_licoreria',
        charset='utf8mb4'
    )

# Ruta de login
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        conn = conectar()
        cur = conn.cursor()
        query = """
            SELECT id_usuario, nombre, rol 
            FROM usuario 
            WHERE correo_electronico = %s AND contrasena = %s
        """
        cur.execute(query, (data['username'], data['password']))
        usuario = cur.fetchone()
    
        if usuario:
            token_data = {
                'user': {
                    'id': usuario[0],
                    'nombre': usuario[1],
                    'rol': usuario[2]
                },
                'exp': datetime.utcnow() + app.config['JWT_EXPIRATION_DELTA']
            }
            token = jwt.encode(token_data, app.config['SECRET_KEY'], algorithm="HS256")
            
            return jsonify({
                'success': True,
                'token': token,
                'usuario': {
                    'id': usuario[0],
                    'nombre': usuario[1],
                    'rol': usuario[2]
                }
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'Credenciales incorrectas'
            }), 401
    except Exception as ex:
        print(f"Error en login: {ex}")
        return jsonify({
            'success': False, 
            'message': 'Error en el login',
            'error': str(ex)
        }), 500
    finally:
        cur.close()
        conn.close()

# Ruta de inicio - Listar productos
@app.route("/")
@token_required
def consulta_general():
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT id_producto, nombre, categoria, precio, cantidad, fecha_vencimiento FROM producto")
        productos = [{
            'id': row[0],
            'nombre': row[1],
            'categoria': row[2],
            'precio': float(row[3]),
            'stock': row[4],
            'fecha_vencimiento': row[5]
        } for row in cur.fetchall()]
        
        return jsonify({'productos': productos, 'success': True})
    except Exception as ex:
        print(f"Error al obtener productos: {ex}")
        return jsonify({'message': 'Error al obtener productos', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Buscar producto por ID
@app.route("/buscar_producto_id/<int:id_producto>", methods=['GET'])
@token_required
def buscar_producto_id(id_producto):
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT id_producto, nombre, categoria, precio, cantidad, fecha_vencimiento
            FROM producto 
            WHERE id_producto = %s
        """, (id_producto,))
        
        producto = cur.fetchone()
        
        if producto:
            return jsonify({
    'success': True,
    'producto': {
        'id': producto[0],
        'id_producto': producto[0],
        'nombre': producto[1],
        'categoria': producto[2],
        'precio': float(producto[3]),
        'cantidad': producto[4],
        'fecha_vencimiento': producto[5]  # CORREGIDO
    }
})
        else:
            return jsonify({'success': False, 'message': 'Producto no encontrado'}), 404
    except Exception as ex:
        print(f"Error en la búsqueda: {ex}")
        return jsonify({'success': False, 'message': 'Error en la búsqueda'}), 500
    finally:
        cur.close()
        conn.close()

# Registrar nuevo producto
@app.route("/registrar", methods=['POST'])
@token_required
def registrar_producto():
    try:
        datos = request.json
        conn = conectar()
        cur = conn.cursor()
        
        # Verificar si el ID ya existe
        cur.execute("SELECT id_producto FROM producto WHERE id_producto = %s", (datos['id_producto'],))
        if cur.fetchone():
            return jsonify({'message': 'El ID de producto ya existe', 'success': False}), 400

        # Insertar nuevo producto
        fecha_venc = datos.get('fecha_vencimiento')
        cur.execute("""
            INSERT INTO producto (id_producto, nombre, categoria, precio, cantidad,fecha_vencimiento)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            datos['id_producto'],
            datos['nombre'],
            datos['categoria'],
            datos['precio'],
            datos['cantidad'],
            fecha_venc
        ))
        conn.commit()
        
        # Registrar actividad
        cur.execute("""
            INSERT INTO registro_actividades (usuario, accion, fecha, detalles)
            VALUES (%s, %s, NOW(), %s)
        """, (
            g.current_user['nombre'],
            'registrar_producto',
          f"Registró producto {datos['nombre']} (ID: {datos['id_producto']}, Vence: {fecha_venc or 'N/A'})"  # CORREGIDO
        ))
        conn.commit()
        
        return jsonify({'message': 'Producto registrado con éxito', 'success': True})
    except Exception as ex:
        conn.rollback()
        print(f"Error al registrar producto: {ex}")
        return jsonify({'message': 'Error al registrar producto', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Eliminar producto
@app.route("/eliminar/<int:id_producto>", methods=['DELETE'])
@token_required
def eliminar_producto(id_producto):
    try:
        conn = conectar()
        cur = conn.cursor()
        
        # Verificar existencia
        cur.execute("SELECT id_producto FROM producto WHERE id_producto = %s", (id_producto,))
        if not cur.fetchone():
            return jsonify({'message': 'Producto no encontrado', 'success': False}), 404
            
        # Eliminar producto
        cur.execute("DELETE FROM producto WHERE id_producto = %s", (id_producto,))
        conn.commit()
        
        # Registrar actividad
        cur.execute("""
            INSERT INTO registro_actividades (usuario, accion, fecha, detalles)
            VALUES (%s, %s, NOW(), %s)
        """, (
            g.current_user['nombre'],
            'eliminar_producto',
            f"Eliminó producto ID {id_producto}"
        ))
        conn.commit()
        
        return jsonify({'message': 'Producto eliminado con éxito', 'success': True})
    except Exception as ex:
        conn.rollback()
        print(f"Error al eliminar producto: {ex}")
        return jsonify({'message': 'Error al eliminar producto', 'success': False}), 500
    finally:
        cur.close()
        conn.close()
@app.route("/actualizar/<int:id_producto>", methods=['PUT'])
@token_required
def actualizar_producto(id_producto):
    try:
        datos = request.json
        conn = conectar()
        cur = conn.cursor()
        
        # Verificar existencia
        cur.execute("SELECT id_producto FROM producto WHERE id_producto = %s", (id_producto,))
        if not cur.fetchone():
            return jsonify({'message': 'Producto no encontrado', 'success': False}), 404
            
        # Actualizar producto
        fecha_venc = datos.get('fecha_vencimiento')
        cur.execute("""
            UPDATE producto 
            SET nombre = %s, categoria = %s, precio = %s, cantidad = %s, fecha_vencimiento = %s
            WHERE id_producto = %s
        """, (
            datos['nombre'],
            datos['categoria'],
            datos['precio'],
            datos['cantidad'],
            fecha_venc,
            id_producto
        ))
        conn.commit()
        
        # Registrar actividad
        cur.execute("""
            INSERT INTO registro_actividades (usuario, accion, fecha, detalles)
            VALUES (%s, %s, NOW(), %s)
        """, (
            g.current_user['nombre'],
            'actualizar_producto',
          f"Actualizó producto ID {id_producto} (Nombre: {datos['nombre']}, Vence: {fecha_venc or 'N/A'})"  # CORREGIDO
        ))
        conn.commit()
        
        return jsonify({'message': 'Producto actualizado con éxito', 'success': True})
    except Exception as ex:
        conn.rollback()
        print(f"Error al actualizar producto: {ex}")
        return jsonify({'message': 'Error al actualizar producto', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Buscar productos
@app.route("/buscar_producto/<string:nombre>", methods=['GET'])
@token_required
def buscar_producto(nombre):
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT id_producto, nombre, categoria, precio, cantidad 
            FROM producto 
           WHERE nombre LIKE %s
        """, (f"%{nombre}%",))
        
        productos = [{
            'id': row[0],
            'nombre': row[1],
            'categoria': row[2],
            'precio': float(row[3]),
            'stock': row[4]
        } for row in cur.fetchall()]
        
        return jsonify({'productos': productos, 'success': True})
    except Exception as ex:
        print(f"Error en la búsqueda: {ex}")
        return jsonify({'message': 'Error en la búsqueda', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Registrar venta
@app.route("/registrar_venta", methods=['POST'])
@token_required
def registrar_venta():
    try:
        datos = request.json
        conn = conectar()
        cur = conn.cursor()
        
        # Obtener ID del usuario que realiza la venta
        id_usuario = g.current_user['id']
        
        # Usar cliente existente si se proporciona ID, sino crear nuevo
        cliente_id = datos.get('cliente_id', 1)  # Default a Consumidor Final
        
        if not datos.get('cliente_id') and datos.get('cliente_nombre'):
            # Crear nuevo cliente solo si no hay ID pero sí nombre
            cur.execute("""
                INSERT INTO cliente (nombre, contacto, cedula) 
                VALUES (%s, %s, %s)
            """, (datos['cliente_nombre'], datos.get('cliente_contacto', ''), datos.get('cliente_cedula', '')))
            cliente_id = cur.lastrowid
        
        # Registrar venta
        cur.execute("""
            INSERT INTO ventas (fecha, id_cliente, total, id_usuario)
            VALUES (NOW(), %s, %s, %s)
        """, (cliente_id, datos['total'], id_usuario))
        venta_id = cur.lastrowid
        
        # Registrar detalles y actualizar stock
        for detalle in datos['detalles']:
            # Verificar stock
            cur.execute("SELECT cantidad FROM producto WHERE id_producto = %s", (detalle['id_producto'],))
            stock = cur.fetchone()[0]
            
            if stock < detalle['cantidad']:
                conn.rollback()
                return jsonify({
                    'message': f'Stock insuficiente para el producto ID {detalle["id_producto"]}',
                    'success': False
                }), 400
            
            # Registrar detalle
            cur.execute("""
                INSERT INTO detalle_ventas (id_venta, id_producto, cantidad, precio_unitario)
                VALUES (%s, %s, %s, %s)
            """, (
                venta_id,
                detalle['id_producto'],
                detalle['cantidad'],
                detalle['precio_unitario']
            ))
            
            # Actualizar stock
            cur.execute("""
                UPDATE producto 
                SET cantidad = cantidad - %s 
                WHERE id_producto = %s
            """, (detalle['cantidad'], detalle['id_producto']))
        
        conn.commit()
        
        # Generar factura PDF
        pdf_path = generar_factura_pdf(venta_id, conn)
        
        # Registrar actividad
        cur.execute("""
            INSERT INTO registro_actividades (usuario, accion, fecha, detalles)
            VALUES (%s, %s, NOW(), %s)
        """, (
            g.current_user['nombre'],
            'registrar_venta',
            f"Registró venta ID {venta_id} por ${datos['total']}"
        ))
        conn.commit()
        
        return jsonify({
            'message': 'Venta registrada con éxito',
            'id_venta': venta_id,
            'pdf_url': f'/facturas/{venta_id}.pdf' if pdf_path else None,
            'success': True
        })
    except Exception as ex:
        conn.rollback()
        print(f"Error al registrar venta: {ex}")
        return jsonify({'message': 'Error al registrar venta', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Generar PDF de factura
def generar_factura_pdf(venta_id, conn):
    try:
        cur = conn.cursor()
        
        # Obtener datos de la venta
        cur.execute("""
            SELECT v.id_venta, v.fecha, v.total, c.nombre as cliente, u.nombre as vendedor
            FROM ventas v
            LEFT JOIN cliente c ON v.id_cliente = c.id_cliente
            JOIN usuario u ON v.id_usuario = u.id_usuario
            WHERE v.id_venta = %s
        """, (venta_id,))
        venta = cur.fetchone()
        
        if not venta:
            return None
        
        # Obtener detalles
        cur.execute("""
            SELECT p.nombre, dv.cantidad, dv.precio_unitario, 
                   (dv.cantidad * dv.precio_unitario) as subtotal
            FROM detalle_ventas dv
            JOIN producto p ON dv.id_producto = p.id_producto
            WHERE dv.id_venta = %s
        """, (venta_id,))
        detalles = cur.fetchall()
        
        # Crear directorio si no existe
        if not os.path.exists('facturas'):
            os.makedirs('facturas')
        
        pdf_path = f'facturas/{venta_id}.pdf'
        
        # Configurar PDF
        pdf = FPDF()
        pdf.add_page()
        
        # Establecer fuentes
        pdf.set_font("Arial", 'B', 16)
        
        # Encabezado
        pdf.cell(0, 10, "LICORERÍA BarInventory", 0, 1, 'C')
        pdf.cell(0, 10, f"FACTURA #{venta[0]}", 0, 1, 'C')
        
        # Información de la venta
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, f"Fecha: {venta[1].strftime('%d/%m/%Y %H:%M')}", 0, 1)
        pdf.cell(0, 10, f"Cliente: {venta[3] or 'Consumidor Final'}", 0, 1)
        pdf.cell(0, 10, f"Vendedor: {venta[4]}", 0, 1)
        pdf.ln(10)
        
        # Tabla de productos
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(100, 10, "Producto", 1, 0, 'C')
        pdf.cell(30, 10, "Cantidad", 1, 0, 'C')
        pdf.cell(30, 10, "P. Unitario", 1, 0, 'C')
        pdf.cell(30, 10, "Subtotal", 1, 1, 'C')
        
        pdf.set_font("Arial", '', 12)
        for detalle in detalles:
            pdf.cell(100, 10, detalle[0], 1)
            pdf.cell(30, 10, str(detalle[1]), 1, 0, 'R')
            pdf.cell(30, 10, f"${detalle[2]:,.2f}", 1, 0, 'R')
            pdf.cell(30, 10, f"${detalle[3]:,.2f}", 1, 1, 'R')
        
        # Total
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(160, 10, "TOTAL:", 1, 0, 'R')
        pdf.cell(30, 10, f"${venta[2]:,.2f}", 1, 1, 'R')
        
        # Guardar PDF
        pdf.output(pdf_path)
        return pdf_path
    except Exception as ex:
        print(f"Error generando factura: {ex}")
        return None

# Descargar factura
@app.route('/facturas/<string:filename>')
@token_required
def descargar_factura(filename):
    try:
        return send_from_directory('facturas', filename, as_attachment=True)
    except Exception as ex:
        print(f"Error al descargar factura: {ex}")
        return jsonify({'message': 'Factura no encontrada', 'success': False}), 404

# Gestión de usuarios (para el panel de admin)
@app.route('/usuarios', methods=['GET'])
@token_required
@admin_required
def obtener_usuarios():
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT id_usuario, nombre, correo_electronico, rol FROM usuario")
        
        usuarios = [{
            'id': row[0],
            'nombre': row[1],
            'correo': row[2],
            'rol': row[3]
        } for row in cur.fetchall()]
        
        return jsonify({'usuarios': usuarios, 'success': True})
    except Exception as ex:
        print(f"Error al obtener usuarios: {ex}")
        return jsonify({'message': 'Error al obtener usuarios', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/registrar_usuario', methods=['POST'])
@token_required
@admin_required
def registrar_usuario():
    try:
        datos = request.json
        conn = conectar()
        cur = conn.cursor()
        
        # Verificar si el correo ya existe
        cur.execute("SELECT id_usuario FROM usuario WHERE correo_electronico = %s", (datos['correo'],))
        if cur.fetchone():
            return jsonify({'message': 'El correo electrónico ya está registrado', 'success': False}), 400

        # Insertar nuevo usuario
        cur.execute("""
            INSERT INTO usuario (nombre, correo_electronico, contrasena, rol)
            VALUES (%s, %s, %s, %s)
        """, (
            datos['nombre'],
            datos['correo'],
            datos['contrasena'],
            datos['rol']
        ))
        conn.commit()
        
        # Registrar actividad
        cur.execute("""
            INSERT INTO registro_actividades (usuario, accion, fecha, detalles)
            VALUES (%s, %s, NOW(), %s)
        """, (
            g.current_user['nombre'],
            'registrar_usuario',
            f"Registró usuario {datos['nombre']} (Correo: {datos['correo']})"
        ))
        conn.commit()
        
        return jsonify({'message': 'Usuario registrado con éxito', 'success': True})
    except Exception as ex:
        conn.rollback()
        print(f"Error al registrar usuario: {ex}")
        return jsonify({'message': 'Error al registrar usuario', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/eliminar_usuario/<int:id_usuario>', methods=['DELETE'])
@token_required
@admin_required
def eliminar_usuario(id_usuario):
    try:
        conn = conectar()
        cur = conn.cursor()
        
        # Verificar existencia
        cur.execute("SELECT id_usuario FROM usuario WHERE id_usuario = %s", (id_usuario,))
        if not cur.fetchone():
            return jsonify({'message': 'Usuario no encontrado', 'success': False}), 404
            
        # No permitir eliminarse a sí mismo
        if id_usuario == g.current_user['id']:
            return jsonify({'message': 'No puedes eliminarte a ti mismo', 'success': False}), 400
            
        # Eliminar usuario
        cur.execute("DELETE FROM usuario WHERE id_usuario = %s", (id_usuario,))
        conn.commit()
        
        # Registrar actividad
        cur.execute("""
            INSERT INTO registro_actividades (usuario, accion, fecha, detalles)
            VALUES (%s, %s, NOW(), %s)
        """, (
            g.current_user['nombre'],
            'eliminar_usuario',
            f"Eliminó usuario ID {id_usuario}"
        ))
        conn.commit()
        
        return jsonify({'message': 'Usuario eliminado con éxito', 'success': True})
    except Exception as ex:
        conn.rollback()
        print(f"Error al eliminar usuario: {ex}")
        return jsonify({'message': 'Error al eliminar usuario', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Reportes para el panel de admin
@app.route('/reportes/ventas_totales', methods=['GET'])
@token_required
@admin_required
def ventas_totales():
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT SUM(total) FROM ventas")
        total = cur.fetchone()[0] or 0
        
        return jsonify({'total': float(total), 'success': True})
    except Exception as ex:
        print(f"Error al obtener ventas totales: {ex}")
        return jsonify({'message': 'Error al obtener ventas totales', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/reportes/productos_mas_vendidos', methods=['GET'])
@token_required
@admin_required
def productos_mas_vendidos():
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT p.nombre, SUM(dv.cantidad) as total_vendido
            FROM detalle_ventas dv
            JOIN producto p ON dv.id_producto = p.id_producto
            GROUP BY p.nombre
            ORDER BY total_vendido DESC
            LIMIT 5
        """)
        
        productos = [{
            'nombre': row[0],
            'total_vendido': row[1]
        } for row in cur.fetchall()]
        
        return jsonify({'productos': productos, 'success': True})
    except Exception as ex:
        print(f"Error al obtener productos más vendidos: {ex}")
        return jsonify({'message': 'Error al obtener productos más vendidos', 'success': False}), 500
    finally:
        cur.close()
        conn.close()
      


# Ruta para historial de ventas
@app.route('/reportes/historial_ventas', methods=['GET'])
@token_required
def historial_ventas():
    try:
        conn = conectar()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT v.id_venta, 
                   DATE_FORMAT(v.fecha, '%d/%m/%Y %H:%i') as fecha, 
                   c.nombre as cliente, 
                   u.nombre as vendedor, 
                   v.total
            FROM ventas v
            LEFT JOIN cliente c ON v.id_cliente = c.id_cliente
            JOIN usuario u ON v.id_usuario = u.id_usuario
            ORDER BY v.fecha DESC
            LIMIT 100
        """)
        
        ventas = [{
            'id': row[0],
            'fecha': row[1],
            'cliente': row[2],
            'vendedor': row[3],
            'total': float(row[4])
        } for row in cur.fetchall()]
        
        return jsonify({'ventas': ventas, 'success': True})
    except Exception as ex:
        print(f"Error al obtener historial de ventas: {ex}")
        return jsonify({'message': 'Error al obtener historial de ventas', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Datos para gráficos
@app.route('/reportes/datos_graficos', methods=['GET'])
@token_required
def datos_graficos():
    try:
        conn = conectar()
        cur = conn.cursor()
        
        # Stock por categoría
        cur.execute("""
            SELECT categoria, SUM(cantidad) 
            FROM producto 
            GROUP BY categoria
        """)
        stock_categorias = {
            'categorias': [],
            'cantidades': []
        }
        for row in cur.fetchall():
            stock_categorias['categorias'].append(row[0])
            stock_categorias['cantidades'].append(row[1] or 0)
        
        # Productos con bajo stock (menos de 10 unidades)
        cur.execute("""
            SELECT nombre, cantidad 
            FROM producto 
            WHERE cantidad < 10 
            ORDER BY cantidad ASC 
            LIMIT 5
        """)
        bajo_stock = {
            'productos': [],
            'stock': []
        }
        for row in cur.fetchall():
            bajo_stock['productos'].append(row[0])
            bajo_stock['stock'].append(row[1])
        
        # Ventas de los últimos 7 días
        cur.execute("""
            SELECT DATE(fecha) as dia, SUM(total) 
            FROM ventas 
            WHERE fecha >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY dia 
            ORDER BY dia
        """)
        ventas_recientes = {
            'fechas': [],
            'totales': []
        }
        for row in cur.fetchall():
            ventas_recientes['fechas'].append(row[0].strftime('%d/%m'))
            ventas_recientes['totales'].append(float(row[1] or 0))
        
        # Productos más vendidos
        cur.execute("""
            SELECT p.nombre, SUM(dv.cantidad) as total_vendido
            FROM detalle_ventas dv
            JOIN producto p ON dv.id_producto = p.id_producto
            GROUP BY p.nombre
            ORDER BY total_vendido DESC
            LIMIT 4
        """)
        top_productos = {
            'nombres': [],
            'cantidades': []
        }
        for row in cur.fetchall():
            top_productos['nombres'].append(row[0])
            top_productos['cantidades'].append(row[1] or 0)
        
        return jsonify({
            'success': True,
            'stock_categorias': stock_categorias,
            'bajo_stock': bajo_stock,
            'ventas_recientes': ventas_recientes,
            'top_productos': top_productos
        })
    except Exception as ex:
        print(f"Error al obtener datos para gráficos: {ex}")
        return jsonify({'success': False, 'message': 'Error al obtener datos para gráficos'}), 500
    finally:
        cur.close()
        conn.close()

# Enviar factura por WhatsApp (simulado)
@app.route('/enviar_whatsapp', methods=['POST'])
@token_required
def enviar_whatsapp():
    try:
        datos = request.json
        # En una implementación real, aquí se integraría con la API de WhatsApp
        print(f"Simulando envío de factura {datos['venta_id']} al número {datos['telefono']}")
        return jsonify({
            'success': True,
            'message': 'Factura enviada por WhatsApp (simulado)'
        })
    except Exception as ex:
        print(f"Error al enviar por WhatsApp: {ex}")
        return jsonify({'success': False, 'message': 'Error al enviar por WhatsApp'}), 500

# Ruta para registrar cliente
@app.route('/registrar_cliente', methods=['POST'])
@token_required
def registrar_cliente():
    try:
        datos = request.json
        conn = conectar()
        cur = conn.cursor()
        
        # Validar que se proporcione cédula
        if not datos.get('cedula'):
            return jsonify({'message': 'La cédula es obligatoria', 'success': False}), 400
        
        # Verificar si la cédula ya existe
        cur.execute("SELECT id_cliente FROM cliente WHERE cedula = %s", (datos['cedula'],))
        if cur.fetchone():
            return jsonify({'message': 'La cédula ya está registrada', 'success': False}), 400
        
        # Insertar nuevo cliente
        cur.execute("""
            INSERT INTO cliente (nombre, contacto, cedula)
            VALUES (%s, %s, %s)
        """, (datos['nombre'], datos['contacto'], datos['cedula']))
        
        conn.commit()
        
        # Registrar actividad
        cur.execute("""
            INSERT INTO registro_actividades (usuario, accion, fecha, detalles)
            VALUES (%s, %s, NOW(), %s)
        """, (
            g.current_user['nombre'],
            'registrar_cliente',
            f"Registró cliente {datos['nombre']} (Cédula: {datos['cedula']})"
        ))
        conn.commit()
        
        return jsonify({'message': 'Cliente registrado con éxito', 'success': True})
    except Exception as ex:
        conn.rollback()
        print(f"Error al registrar cliente: {ex}")
        return jsonify({'message': 'Error al registrar cliente', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Ruta para listar clientes
@app.route('/clientes', methods=['GET'])
@token_required
def obtener_clientes():
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT id_cliente, nombre, contacto, cedula,
                   DATE_FORMAT(NOW(), '%d/%m/%Y') as fecha_registro 
            FROM cliente
        """)
        
        clientes = [{
            'id': row[0],
            'nombre': row[1],
            'contacto': row[2],
            'cedula': row[3],
            'fecha_registro': row[4]
        } for row in cur.fetchall()]
        
        return jsonify({'clientes': clientes, 'success': True})
    except Exception as ex:
        print(f"Error al obtener clientes: {ex}")
        return jsonify({'message': 'Error al obtener clientes', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Ruta para actualizar cliente
@app.route('/actualizar_cliente/<int:id_cliente>', methods=['PUT'])
@token_required
def actualizar_cliente(id_cliente):
    try:
        datos = request.json
        conn = conectar()
        cur = conn.cursor()
        
        # Validar que se proporcione cédula
        if not datos.get('cedula'):
            return jsonify({'message': 'La cédula es obligatoria', 'success': False}), 400
        
        # Verificar si la cédula ya existe en otro cliente
        cur.execute("SELECT id_cliente FROM cliente WHERE cedula = %s AND id_cliente != %s", 
                   (datos['cedula'], id_cliente))
        if cur.fetchone():
            return jsonify({'message': 'La cédula ya está registrada en otro cliente', 'success': False}), 400
        
        # Actualizar cliente
        cur.execute("""
            UPDATE cliente 
            SET nombre = %s, contacto = %s, cedula = %s
            WHERE id_cliente = %s
        """, (datos['nombre'], datos['contacto'], datos['cedula'], id_cliente))
        
        conn.commit()
        
        # Registrar actividad
        cur.execute("""
            INSERT INTO registro_actividades (usuario, accion, fecha, detalles)
            VALUES (%s, %s, NOW(), %s)
        """, (
            g.current_user['nombre'],
            'actualizar_cliente',
            f"Actualizó cliente ID {id_cliente} a {datos['nombre']}"
        ))
        conn.commit()
        
        return jsonify({'message': 'Cliente actualizado con éxito', 'success': True})
    except Exception as ex:
        conn.rollback()
        print(f"Error al actualizar cliente: {ex}")
        return jsonify({'message': 'Error al actualizar cliente', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Ruta para eliminar cliente
@app.route('/eliminar_cliente/<int:id_cliente>', methods=['DELETE'])
@token_required
def eliminar_cliente(id_cliente):
    try:
        conn = conectar()
        cur = conn.cursor()
        
        # Verificar si el cliente existe
        cur.execute("SELECT id_cliente FROM cliente WHERE id_cliente = %s", (id_cliente,))
        if not cur.fetchone():
            return jsonify({'message': 'Cliente no encontrado', 'success': False}), 404
            
        # Verificar si el cliente tiene ventas asociadas
        cur.execute("SELECT id_venta FROM ventas WHERE id_cliente = %s", (id_cliente,))
        if cur.fetchone():
            return jsonify({
                'message': 'No se puede eliminar el cliente porque tiene ventas asociadas',
                'success': False
            }), 400
        
        # Eliminar cliente
        cur.execute("DELETE FROM cliente WHERE id_cliente = %s", (id_cliente,))
        conn.commit()
        
        # Registrar actividad
        cur.execute("""
            INSERT INTO registro_actividades (usuario, accion, fecha, detalles)
            VALUES (%s, %s, NOW(), %s)
        """, (
            g.current_user['nombre'],
            'eliminar_cliente',
            f"Eliminó cliente ID {id_cliente}"
        ))
        conn.commit()
        
        return jsonify({'message': 'Cliente eliminado con éxito', 'success': True})
    except Exception as ex:
        conn.rollback()
        print(f"Error al eliminar cliente: {ex}")
        return jsonify({'message': 'Error al eliminar cliente', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Reporte de ventas por período
@app.route('/reportes/ventas_por_periodo', methods=['GET'])
@token_required
def ventas_por_periodo():
    try:
        periodo = request.args.get('periodo', 'month')  # day, week, month, year
        conn = conectar()
        cur = conn.cursor()
        
        # Definir el intervalo de tiempo según el período seleccionado
        if periodo == 'day':
            interval = '1 DAY'
            date_format = '%H:00'
            group_by = 'HOUR(v.fecha)'
        elif periodo == 'week':
            interval = '1 WEEK'
            date_format = '%a %d'
            group_by = 'DAY(v.fecha)'
        elif periodo == 'year':
            interval = '1 YEAR'
            date_format = '%b %Y'
            group_by = 'MONTH(v.fecha)'
        else:  # month por defecto
            interval = '1 MONTH'
            date_format = '%d %b'
            group_by = 'DAY(v.fecha)'
        
        cur.execute(f"""
            SELECT DATE_FORMAT(v.fecha, %s) as fecha, SUM(v.total) as total
            FROM ventas v
            WHERE v.fecha >= DATE_SUB(NOW(), INTERVAL {interval})
            GROUP BY {group_by}
            ORDER BY v.fecha
        """, (date_format,))
        
        datos = cur.fetchall()
        
        return jsonify({
            'success': True,
            'labels': [row[0] for row in datos],
            'data': [float(row[1] or 0) for row in datos]
        })
    except Exception as ex:
        print(f"Error al obtener ventas por período: {ex}")
        return jsonify({'success': False, 'message': 'Error al obtener ventas por período'}), 500
    finally:
        cur.close()
        conn.close()

# Reporte de productos más vendidos con filtros
@app.route('/reportes/productos_mas_vendidos_filtrados', methods=['GET'])
@token_required
def productos_mas_vendidos_filtrados():
    try:
        categoria = request.args.get('categoria', '')
        limite = request.args.get('limite', 5, type=int)
        
        conn = conectar()
        cur = conn.cursor()
        
        query = """
            SELECT p.nombre, SUM(dv.cantidad) as total_vendido
            FROM detalle_ventas dv
            JOIN producto p ON dv.id_producto = p.id_producto
        """
        
        params = []
        
        if categoria:
            query += " WHERE p.categoria = %s"
            params.append(categoria)
        
        query += """
            GROUP BY p.nombre
            ORDER BY total_vendido DESC
            LIMIT %s
        """
        params.append(limite)
        
        cur.execute(query, params)
        
        productos = [{
            'nombre': row[0],
            'total_vendido': row[1]
        } for row in cur.fetchall()]
        
        return jsonify({'success': True, 'productos': productos})
    except Exception as ex:
        print(f"Error al obtener productos más vendidos: {ex}")
        return jsonify({'success': False, 'message': 'Error al obtener productos más vendidos'}), 500
    finally:
        cur.close()
        conn.close()

# Reporte de estadísticas generales
@app.route('/reportes/estadisticas_generales', methods=['GET'])
@token_required
def estadisticas_generales():
    try:
        conn = conectar()
        cur = conn.cursor()
        
        # Ventas totales del mes actual
        cur.execute("""
            SELECT SUM(total) 
            FROM ventas 
            WHERE fecha >= DATE_FORMAT(NOW(), '%Y-%m-01')
        """)
        ventas_mes_actual = cur.fetchone()[0] or 0
        
        # Ventas totales del mes anterior
        cur.execute("""
            SELECT SUM(total) 
            FROM ventas 
            WHERE fecha BETWEEN DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 1 MONTH), '%Y-%m-01') 
            AND LAST_DAY(DATE_SUB(NOW(), INTERVAL 1 MONTH))
        """)
        ventas_mes_anterior = cur.fetchone()[0] or 0
        
        # Variación porcentual
        variacion = ((ventas_mes_actual - ventas_mes_anterior) / ventas_mes_anterior * 100) if ventas_mes_anterior else 0
        
        # Productos vendidos este mes
        cur.execute("""
            SELECT SUM(dv.cantidad)
            FROM detalle_ventas dv
            JOIN ventas v ON dv.id_venta = v.id_venta
            WHERE v.fecha >= DATE_FORMAT(NOW(), '%Y-%m-01')
        """)
        productos_vendidos = cur.fetchone()[0] or 0
        
        # Clientes nuevos este mes
        cur.execute("""
            SELECT COUNT(*) 
            FROM cliente 
            WHERE DATE(fecha_registro) >= DATE_FORMAT(NOW(), '%Y-%m-01')
        """)
        clientes_nuevos = cur.fetchone()[0] or 0
        
        # Ticket promedio
        cur.execute("""
            SELECT AVG(total) 
            FROM ventas 
            WHERE fecha >= DATE_FORMAT(NOW(), '%Y-%m-01')
        """)
        ticket_promedio = cur.fetchone()[0] or 0
        
        # Productos con bajo stock
        cur.execute("SELECT COUNT(*) FROM producto WHERE cantidad < 10")
        bajo_stock = cur.fetchone()[0] or 0
        
        # Total productos
        cur.execute("SELECT COUNT(*) FROM producto")
        total_productos = cur.fetchone()[0] or 0
        
        return jsonify({
            'success': True,
            'estadisticas': {
                'ventas_mes_actual': float(ventas_mes_actual),
                'variacion_ventas': float(variacion),
                'productos_vendidos': productos_vendidos,
                'clientes_nuevos': clientes_nuevos,
                'ticket_promedio': float(ticket_promedio),
                'bajo_stock': bajo_stock,
                'total_productos': total_productos
            }
        })
    except Exception as ex:
        print(f"Error al obtener estadísticas: {ex}")
        return jsonify({'success': False, 'message': 'Error al obtener estadísticas'}), 500
    finally:
        cur.close()
        conn.close()

# Reporte de mejores vendedores
@app.route('/reportes/mejores_vendedores', methods=['GET'])
@token_required
def mejores_vendedores():
    try:
        limite = request.args.get('limite', 5, type=int)
        
        conn = conectar()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT u.nombre, SUM(v.total) as total_ventas
            FROM ventas v
            JOIN usuario u ON v.id_usuario = u.id_usuario
            WHERE v.fecha >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
            GROUP BY u.nombre
            ORDER BY total_ventas DESC
            LIMIT %s
        """, (limite,))
        
        vendedores = [{
            'nombre': row[0],
            'total_ventas': float(row[1])
        } for row in cur.fetchall()]
        
        return jsonify({'success': True, 'vendedores': vendedores})
    except Exception as ex:
        print(f"Error al obtener mejores vendedores: {ex}")
        return jsonify({'success': False, 'message': 'Error al obtener mejores vendedores'}), 500
    finally:
        cur.close()
        conn.close()

# Mejorar la función de alertas para incluir anticipación
@app.route('/alertas', methods=['GET'])
@token_required
def obtener_alertas():
    try:
        conn = conectar()
        cur = conn.cursor()
        
        # Productos con bajo stock (menos de 10 unidades)
        cur.execute("""
            SELECT id_producto, nombre, categoria, precio, cantidad 
            FROM producto 
            WHERE cantidad < 10
            ORDER BY cantidad ASC
        """)
        bajo_stock = [{
            'id': row[0],
            'nombre': row[1],
            'categoria': row[2],
            'precio': float(row[3]),
            'cantidad': row[4],
            'tipo': 'stock'
        } for row in cur.fetchall()]
        
        # Productos por vencer (en menos de 30, 15 y 7 días)
        cur.execute("""
            SELECT id_producto, nombre, categoria, precio, cantidad,
                   DATE_FORMAT(fecha_vencimiento, '%d/%m/%Y') as fecha_vencimiento,
                   DATEDIFF(fecha_vencimiento, CURDATE()) as dias_restantes
            FROM producto 
            WHERE fecha_vencimiento IS NOT NULL 
            AND fecha_vencimiento BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
            ORDER BY fecha_vencimiento ASC
        """)
        por_vencer = [{
            'id': row[0],
            'nombre': row[1],
            'categoria': row[2],
            'precio': float(row[3]),
            'cantidad': row[4],
            'fecha_vencimiento': row[5],
            'dias_restantes': row[6],
            'prioridad': 'baja' if row[6] > 15 else 'media' if row[6] > 7 else 'alta',
            'tipo': 'vencimiento'
        } for row in cur.fetchall()]
        
        return jsonify({
            'success': True,
            'bajo_stock': bajo_stock,
            'por_vencer': por_vencer,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as ex:
        print(f"Error al obtener alertas: {ex}")
        return jsonify({
            'success': False,
            'message': 'Error al obtener alertas'
        }), 500
    finally:
        cur.close()
        conn.close()

# Obtener registro de actividades
@app.route('/registro_actividades', methods=['GET'])
@token_required
@admin_required
def obtener_registro_actividades():
    try:
        conn = conectar()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id_actividad, usuario, accion, fecha, detalles 
            FROM registro_actividades 
            ORDER BY fecha DESC 
            LIMIT 100
        """)
        
        actividades = [{
            'id': row[0],
            'usuario': row[1],
            'accion': row[2],
            'fecha': row[3].strftime('%d/%m/%Y %H:%M') if row[3] else '',
            'detalles': row[4]
        } for row in cur.fetchall()]
        
        return jsonify({'actividades': actividades, 'success': True})
    except Exception as ex:
        print(f"Error al obtener registro de actividades: {ex}")
        return jsonify({'message': 'Error al obtener registro de actividades', 'success': False}), 500
    finally:
        cur.close()
        conn.close()

# Verificar estado del servidor
@app.route('/health', methods=['GET'])
def health_check():
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except Exception as e:
        print(f"Error en health check: {e}")
        return jsonify({'status': 'unhealthy', 'database': 'disconnected', 'error': str(e)}), 500
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    # Crear directorio para facturas si no existe
    if not os.path.exists('facturas'):
        os.makedirs('facturas')
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
