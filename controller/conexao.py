import pymysql

# Configurações do banco de dados
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '1234',
    'database': 'banco'
}

def conectar():
    try:
        conn = pymysql.connect(**db_config)
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS arquivos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    pessoa_id INT,
                    nome_arquivo VARCHAR(255),
                    CONSTRAINT fk_pessoa
                        FOREIGN KEY (pessoa_id)
                        REFERENCES formulario (id)
                        ON DELETE CASCADE
                )
            ''')
        return conn
    except pymysql.Error as error:
        print("Erro ao conectar ao banco de dados: ", error)
        return None

