from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector
from datetime import datetime

app = Flask(__name__)
app.secret_key = "logitract_neu_key_2024"

def connect_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="3007", 
        database="InventorySystem"
    )

@app.route('/')
def index():
    conn = connect_db()
    cursor = conn.cursor()
    
    # 1. Báo cáo tồn kho
    query_inventory = """
        SELECT w.WarehouseName, p.ProductName, p.UnitPrice, SUM(ih.Quantity) 
        FROM INVENTORYHISTORY ih
        JOIN WAREHOUSES w ON ih.WarehouseID = w.WarehouseID
        JOIN PRODUCTS p ON ih.ProductID = p.ProductID
        GROUP BY w.WarehouseName, p.ProductName, p.UnitPrice
    """
    cursor.execute(query_inventory)
    inventory = cursor.fetchall()
    
    # 2. Cảnh báo tồn kho THEO TỪNG KHO (Sửa lại logic lấy dữ liệu)
    cursor.execute("""
        SELECT w.WarehouseName, p.ProductName, SUM(ih.Quantity) as Total 
        FROM PRODUCTS p 
        JOIN INVENTORYHISTORY ih ON p.ProductID = ih.ProductID 
        JOIN WAREHOUSES w ON ih.WarehouseID = w.WarehouseID
        GROUP BY w.WarehouseName, p.ProductName 
        HAVING Total < 30
    """)
    alerts = cursor.fetchall()

    # 3. Danh bạ đối tác
    cursor.execute("SELECT SupplierID, SupplierName, Address, PhoneNumber FROM SUPPLIERS")
    suppliers = cursor.fetchall()

    # 4. Danh sách sản phẩm (Cho Dropdown)
    cursor.execute("SELECT ProductID, ProductName FROM PRODUCTS")
    all_products = cursor.fetchall()

    # 5. Danh sách Kho bãi (MỚI)
    cursor.execute("SELECT WarehouseID, WarehouseName, Address FROM WAREHOUSES")
    warehouses = cursor.fetchall()

    # 6. Lịch sử giao dịch (MỚI)
    query_history = """
        SELECT ih.TransactionDate, p.ProductName, w.WarehouseName, ih.Quantity 
        FROM INVENTORYHISTORY ih
        JOIN PRODUCTS p ON ih.ProductID = p.ProductID
        JOIN WAREHOUSES w ON ih.WarehouseID = w.WarehouseID
        ORDER BY ih.TransactionDate DESC LIMIT 50
    """
    cursor.execute(query_history)
    history = cursor.fetchall()
    
    conn.close()
    return render_template('index.html', 
                           inventory=inventory, alerts=alerts, 
                           suppliers=suppliers, all_products=all_products,
                           warehouses=warehouses, history=history)

# --- CÁC HÀM XỬ LÝ (GIỮ NGUYÊN) ---
@app.route('/add', methods=['POST'])
def add_product():
    try:
        p_id, p_name, p_desc, p_price, p_supp = request.form['p_id'], request.form['p_name'], request.form['p_desc'], request.form['p_price'], request.form['p_supp']
        conn = connect_db(); cursor = conn.cursor()
        cursor.execute("INSERT INTO PRODUCTS (ProductID, ProductName, Description, UnitPrice, SupplierID) VALUES (%s, %s, %s, %s, %s)", (int(p_id), p_name, p_desc, float(p_price), int(p_supp)))
        conn.commit(); conn.close()
        flash(f"Thành công: Đã tạo mã hàng '{p_name}'", "success")
    except Exception as e: flash(f"Lỗi: {e}", "danger")
    return redirect(url_for('index'))

@app.route('/update', methods=['POST'])
def update_product():
    try:
        u_id, u_price, u_desc = request.form['u_id'], request.form.get('u_price'), request.form.get('u_desc')
        conn = connect_db(); cursor = conn.cursor()
        if u_price: cursor.execute("UPDATE PRODUCTS SET UnitPrice = %s WHERE ProductID = %s", (float(u_price), int(u_id)))
        if u_desc: cursor.execute("UPDATE PRODUCTS SET Description = %s WHERE ProductID = %s", (u_desc, int(u_id)))
        conn.commit(); conn.close()
        flash("Cập nhật thông tin hàng hóa thành công!", "success")
    except Exception as e: flash(f"Lỗi cập nhật: {e}", "danger")
    return redirect(url_for('index'))

@app.route('/transaction', methods=['POST'])
def transaction():
    try:
        t_id = request.form['t_id']
        t_qty = int(request.form['t_qty'])
        t_type = request.form['t_type']
        t_warehouse = request.form['t_warehouse']
        
        conn = connect_db()
        cursor = conn.cursor()
        
        # NẾU LÀ LỆNH XUẤT KHO -> KIỂM TRA SỐ LƯỢNG TỒN TRƯỚC
        if t_type == 'OUT':
            # Truy vấn số lượng đang có của Sản phẩm này tại Kho này
            cursor.execute("""
                SELECT SUM(Quantity) 
                FROM INVENTORYHISTORY 
                WHERE ProductID = %s AND WarehouseID = %s
            """, (int(t_id), int(t_warehouse)))
            
            result = cursor.fetchone()[0]
            current_stock = int(result) if result else 0
            
            # Nếu số lượng tồn nhỏ hơn số lượng muốn xuất -> Chặn giao dịch
            if current_stock < t_qty:
                conn.close()
                flash(f"Giao dịch thất bại: Kho này hiện chỉ còn {current_stock} sản phẩm, không đủ để xuất {t_qty}!", "danger")
                return redirect(url_for('index'))
                
            t_qty = -t_qty # Chuyển thành số âm để trừ kho
            
        # Gọi Procedure để thực thi giao dịch nếu hợp lệ
        transaction_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.callproc('sp_RestockProduct', [int(t_id), int(t_warehouse), t_qty, transaction_date])
        
        conn.commit()
        conn.close()
        
        action = "Nhập" if t_type == "IN" else "Xuất"
        flash(f"Thực thi lệnh {action} kho thành công!", "success")
        
    except Exception as e:
        flash(f"Lỗi giao dịch: {e}", "danger")
    return redirect(url_for('index'))

@app.route('/add_supplier', methods=['POST'])
def add_supplier():
    try:
        s_name, s_addr, s_phone = request.form['s_name'], request.form['s_address'], request.form['s_phone']
        conn = connect_db(); cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(MAX(SupplierID), 0) + 1 FROM SUPPLIERS")
        next_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO SUPPLIERS (SupplierID, SupplierName, Address, PhoneNumber) VALUES (%s, %s, %s, %s)", (next_id, s_name, s_addr, s_phone))
        conn.commit(); conn.close()
        flash(f"Đã thêm đối tác '{s_name}' vào danh bạ!", "success")
    except Exception as e: flash(f"Lỗi: {e}", "danger")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
