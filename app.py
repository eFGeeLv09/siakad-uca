import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import csv
import io

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'kunci_rahasia_siakad_sangat_aman_uca')

def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', 3306)),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'siakad_db'),
        cursorclass=pymysql.cursors.DictCursor,
        ssl={'ssl': {}} if os.environ.get('DB_HOST') else None
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    pesan_error = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']
        
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute('SELECT * FROM admin WHERE username = %s', (username,))
                akun = cursor.fetchone()
                
                if akun and (akun['password'] == password or check_password_hash(akun['password'], password)):
                    session['loggedin'] = True
                    session['username'] = akun['username']
                    session['role'] = 'admin'
                    conn.close()
                    return redirect(url_for('index', tab='dashboard'))
                
                cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
                user = cursor.fetchone()
                
            conn.close()
            
            if user and (user['password'] == password or check_password_hash(user['password'], password)):
                session['loggedin'] = True
                session['username'] = user['username']
                session['role'] = 'user'
                return redirect(url_for('index', tab='dashboard'))
            else:
                pesan_error = 'Username atau Password salah!'
                
        except Exception as e:
            pesan_error = f'Koneksi Database Gagal: {e}'
            
    return render_template('login.html', pesan=pesan_error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    pesan = ''
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            pesan = 'Username dan password wajib diisi!'
        else:
            try:
                conn = get_db_connection()
                with conn.cursor() as cursor:
                    cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
                    akun_ada = cursor.fetchone()
                    
                    if akun_ada:
                        pesan = 'Username sudah terpakai!'
                    else:
                        hashed_password = generate_password_hash(password)
                        cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (username, hashed_password, 'user'))
                        conn.commit()
                        flash('Registrasi berhasil! Silakan login.', 'success')
                        return redirect(url_for('login'))
                conn.close()
            except Exception as e:
                pesan = f'Terjadi kesalahan database: {e}'
            
    return render_template('register.html', pesan=pesan)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    active_tab = request.args.get('tab', 'dashboard')
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    with conn.cursor() as cursor:
        query_dosen = "SELECT * FROM dosen WHERE 1=1"
        params_dosen = []
        if search_query and active_tab == 'dosen':
            query_dosen += " AND (nidn LIKE %s OR nama_dosen LIKE %s OR keahlian LIKE %s)"
            params_dosen.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        cursor.execute(query_dosen, params_dosen)
        data_dosen = cursor.fetchall()
        
        query_mhs = "SELECT * FROM mahasiswa WHERE 1=1"
        params_mhs = []
        if search_query and active_tab == 'mahasiswa':
            query_mhs += " AND (nim LIKE %s OR nama_mahasiswa LIKE %s OR prodi LIKE %s)"
            params_mhs.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        cursor.execute(query_mhs, params_mhs)
        data_mahasiswa = cursor.fetchall()
        
        query_mk = "SELECT * FROM mata_kuliah WHERE 1=1"
        params_mk = []
        if search_query and active_tab == 'matkul':
            query_mk += " AND (kode_mk LIKE %s OR nama_mk LIKE %s)"
            params_mk.extend([f"%{search_query}%", f"%{search_query}%"])
        cursor.execute(query_mk, params_mk)
        data_matkul = cursor.fetchall()
        
        query_krs = """
            SELECT k.id_krs, m.nama_mahasiswa, mk.nama_mk, k.semester, k.nilai_huruf 
            FROM krs k
            JOIN mahasiswa m ON k.nim_mhs = m.nim
            JOIN mata_kuliah mk ON k.kode_mk = mk.kode_mk
            WHERE 1=1
        """
        params_krs = []
        
        if session.get('role') == 'user':
            query_krs += " AND m.nama_mahasiswa LIKE %s"
            params_krs.append(f"%{session['username']}%")
            
        if search_query and active_tab == 'krs':
            query_krs += " AND (m.nama_mahasiswa LIKE %s OR mk.nama_mk LIKE %s OR k.semester LIKE %s)"
            params_krs.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
            
        cursor.execute(query_krs, params_krs)
        data_krs = cursor.fetchall()

        cursor.execute("SELECT SUM(sks) AS total_sks FROM mata_kuliah")
        res_sks = cursor.fetchone()
        total_sks = res_sks['total_sks'] if res_sks and res_sks['total_sks'] else 0

    conn.close()
    
    return render_template(
        'index.html', 
        dosen=data_dosen, 
        mahasiswa=data_mahasiswa, 
        matkul=data_matkul, 
        krs=data_krs, 
        total_sks=total_sks,
        username=session['username'],
        role=session.get('role', 'user'),
        search=search_query,
        active_tab=active_tab
    )

@app.route('/export_csv/<table_name>')
def export_csv(table_name):
    if 'loggedin' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    with conn.cursor() as cursor:
        if table_name == 'mahasiswa':
            cursor.execute("SELECT nim, nama_mahasiswa, prodi, kelas FROM mahasiswa")
            filename = "Data_Mahasiswa_UCA.csv"
        elif table_name == 'dosen':
            cursor.execute("SELECT nidn, nama_dosen, keahlian FROM dosen")
            filename = "Data_Dosen_UCA.csv"
        elif table_name == 'matkul':
            cursor.execute("SELECT kode_mk, nama_mk, sks FROM mata_kuliah")
            filename = "Data_MataKuliah_UCA.csv"
        elif table_name == 'krs':
            cursor.execute("""
                SELECT m.nama_mahasiswa, mk.nama_mk, k.semester, k.nilai_huruf 
                FROM krs k JOIN mahasiswa m ON k.nim_mhs = m.nim JOIN mata_kuliah mk ON k.kode_mk = mk.kode_mk
            """)
            filename = "Data_KRS_UCA.csv"
        else:
            conn.close()
            return redirect(url_for('index'))
            
        data = cursor.fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    if data:
        writer.writerow(data[0].keys())
        for row in data:
            writer.writerow(row.values())
            
    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route('/tambah_mahasiswa', methods=['POST'])
def tambah_mahasiswa():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO mahasiswa (nim, nama_mahasiswa, prodi, kelas) VALUES (%s, %s, %s, %s)", 
                           (request.form['nim'], request.form['nama_mahasiswa'], request.form['prodi'], request.form['kelas']))
            conn.commit()
        conn.close()
        flash('Data mahasiswa berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambah mahasiswa (NIM mungkin sudah terdaftar): {e}', 'error')
    return redirect(url_for('index', tab='mahasiswa'))

@app.route('/tambah_dosen', methods=['POST'])
def tambah_dosen():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO dosen (nidn, nidn_dosen, nama_dosen, keahlian) VALUES (%s, %s, %s, %s)", 
                           (request.form['nidn'], '', request.form['nama_dosen'], request.form['keahlian']))
            conn.commit()
        conn.close()
        flash('Data dosen berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambah dosen (NIDN mungkin sudah terdaftar): {e}', 'error')
    return redirect(url_for('index', tab='dosen'))

@app.route('/tambah_matkul', methods=['POST'])
def tambah_matkul():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO mata_kuliah (kode_mk, nama_mk, sks, nidn_dosen) VALUES (%s, %s, %s, %s)", 
                           (request.form['kode_mk'], request.form['nama_mk'], request.form['sks'], request.form.get('nidn_dosen')))
            conn.commit()
        conn.close()
        flash('Mata kuliah berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambah mata kuliah (Kode MK mungkin sudah ada): {e}', 'error')
    return redirect(url_for('index', tab='matkul'))

@app.route('/tambah_krs', methods=['POST'])
def tambah_krs():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO krs (nim_mhs, kode_mk, semester, nilai_huruf) VALUES (%s, %s, %s, %s)", 
                           (request.form['nim_mhs'], request.form['kode_mk'], request.form['semester'], request.form['nilai_huruf']))
            conn.commit()
        conn.close()
        flash('Data KRS & nilai berhasil disimpan!', 'success')
    except Exception as e:
        flash(f'Gagal menyimpan KRS: {e}', 'error')
    return redirect(url_for('index', tab='krs'))

@app.route('/edit_mahasiswa/<nim>', methods=['POST'])
def edit_mahasiswa(nim):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE mahasiswa SET nama_mahasiswa=%s, prodi=%s, kelas=%s WHERE nim=%s", 
                           (request.form['nama_mahasiswa'], request.form['prodi'], request.form['kelas'], nim))
            conn.commit()
        conn.close()
        flash('Data mahasiswa berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui data mahasiswa: {e}', 'error')
    return redirect(url_for('index', tab='mahasiswa'))

@app.route('/edit_dosen/<nidn>', methods=['POST'])
def edit_dosen(nidn):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE dosen SET nama_dosen=%s, keahlian=%s WHERE nidn=%s", 
                           (request.form['nama_dosen'], request.form['keahlian'], nidn))
            conn.commit()
        conn.close()
        flash('Data dosen berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui data dosen: {e}', 'error')
    return redirect(url_for('index', tab='dosen'))

@app.route('/edit_matkul/<kode_mk>', methods=['POST'])
def edit_matkul(kode_mk):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE mata_kuliah SET nama_mk=%s, sks=%s, nidn_dosen=%s WHERE kode_mk=%s", 
                           (request.form['nama_mk'], request.form['sks'], request.form.get('nidn_dosen'), kode_mk))
            conn.commit()
        conn.close()
        flash('Mata kuliah berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui mata kuliah: {e}', 'error')
    return redirect(url_for('index', tab='matkul'))

@app.route('/edit_krs/<int:id_krs>', methods=['POST'])
def edit_krs(id_krs):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE krs SET semester=%s, nilai_huruf=%s WHERE id_krs=%s", 
                           (request.form['semester'], request.form['nilai_huruf'], id_krs))
            conn.commit()
        conn.close()
        flash('Data KRS & nilai berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui KRS: {e}', 'error')
    return redirect(url_for('index', tab='krs'))

@app.route('/hapus_mahasiswa/<nim>')
def hapus_mahasiswa(nim):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM mahasiswa WHERE nim = %s", (nim,))
            conn.commit()
        conn.close()
        flash('Data mahasiswa berhasil dihapus.', 'success')
    except Exception:
        flash('Mahasiswa tidak dapat dihapus karena masih memiliki data KRS aktif!', 'error')
    return redirect(url_for('index', tab='mahasiswa'))

@app.route('/hapus_dosen/<nidn>')
def hapus_dosen(nidn):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM dosen WHERE nidn = %s", (nidn,))
            conn.commit()
        conn.close()
        flash('Data dosen berhasil dihapus.', 'success')
    except Exception:
        flash('Dosen tidak dapat dihapus karena masih mengampu mata kuliah!', 'error')
    return redirect(url_for('index', tab='dosen'))

@app.route('/hapus_matkul/<kode_mk>')
def hapus_matkul(kode_mk):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM mata_kuliah WHERE kode_mk = %s", (kode_mk,))
            conn.commit()
        conn.close()
        flash('Mata kuliah berhasil dihapus.', 'success')
    except Exception:
        flash('Mata kuliah tidak dapat dihapus karena masih terdata di KRS mahasiswa!', 'error')
    return redirect(url_for('index', tab='matkul'))

@app.route('/hapus_krs/<int:id_krs>')
def hapus_krs(id_krs):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM krs WHERE id_krs = %s", (id_krs,))
            cursor.execute("ALTER TABLE krs AUTO_INCREMENT = 1")
            conn.commit()
        conn.close()
        flash('Data KRS berhasil dihapus.', 'success')
    except Exception as e:
        flash(f'Gagal menghapus KRS: {e}', 'error')
    return redirect(url_for('index', tab='krs'))

if __name__ == '__main__':
    app.run(debug=True)