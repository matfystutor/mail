# import pkg_resources ##required on my setup to use MySQLdb
# pkg_resources.require("MySQL-python")  ##required on my setup to use MySQLdb
# import MySQLdb as mdb
import mysql.connector
from tkmail.config import HOSTNAME, USERNAME, PASSWORD, DATABASE


class Error(Exception):
    """Base class of my own error types"""
    def __init__(self, msg):
        super(Error, self).__init__()
        self.msg = msg


class DatabaseError(Error):
    def __init__(self, mdbError):
        super(DatabaseError, self).__init__('Error %d: %s'
                % (mdbError.args[0], mdbError.args[1]))


class Database(object):
    tkfolk_schema = """
        id      int(11)      NO   None  primary, auto_increment
        navn    varchar(50)  YES  None
        email   varchar(50)  YES  None
        accepteremail
                char(3)      YES  ja
        accepterdirektemail
                char(3)      NO   Ja
        gade    varchar(50)  YES  None
        husnr   varchar(15)  YES  None
        postnr  varchar(10)  YES  None
        postby  varchar(25)  YES  None
        land    varchar(50)  YES  None
        gone    char(3)      NO   nej
        tlf     varchar(20)  YES  None
        note    text         YES  None
        """

    def __init__(self):
        try:
            if HOSTNAME != '127.0.0.1':
                raise ValueError('Non-local hostname not supported by ' +
                                 'mysql.connector')
            self._mysql = mysql.connector.Connect(
                user=USERNAME, password=PASSWORD, database=DATABASE)
        except mdb.Error as e:
            raise DatabaseError(e)

        self._cursor = self._mysql.cursor()

    def _execute(self, statement, *args):
        if args:
            sql = statement % args
        else:
            sql = statement
        try:
            self._cursor.execute(sql)
        except mdb.Error as e:
            raise DatabaseError(e)

    def _fetchall(self, *args, **kwargs):
        column = kwargs.pop('column', None)
        self._execute(*args)
        rows = self._cursor.fetchall()
        if column is not None:
            return [row[column] for row in rows]
        else:
            return list(rows)

    def get_people(self, **kwargs):
        column_list = ("id navn email accepteremail accepterdirektemail "
                "gade husnr postnr postby land gone tlf note".split())
        columns = ', '.join("`%s`" % column for column in column_list)

        clauses = []
        for k, v in kwargs.items():
            if k == 'id__in':
                id_string = ','.join('"%s"' % each for each in v)
                clauses.push(('`id` IN %s', id_string))
            else:
                raise TypeError('unknown kwarg "%s"' % k)

        if clauses:
            where_clause = ' AND '.join(expr for expr, param in clauses)
        else:
            where_clause = "1"

        format_args = [param for expr, param in clauses]

        rows = self._fetchall("SELECT %s FROM `tkfolk` WHERE %s"
            % (columns, where_clause), *format_args)

        return [dict(zip(column_list, row)) for row in rows]

    def get_email_addresses(self, id_list):
        id_string = ','.join(str(each) for each in id_list)
        return self._fetchall("""
            SELECT `email` FROM `tkfolk`
            WHERE `id` IN (%s)
            AND `accepterdirektemail`='Ja'
            """, id_string, column=0)

    def get_admin_emails(self):
        return self._fetchall("""
            SELECT `tkfolk`.`email`
            FROM `tkfolk`, `grupper`,`gruppemedlemmer`
            WHERE `grupper`.`navn`='admin'
            AND `gruppemedlemmer`.`gruppeid`=`grupper`.`id`
            AND `gruppemedlemmer`.`personid`= `tkfolk`.`id`
            """, column=0)

    def get_groups(self):
        return self._fetchall("""
            SELECT `id`,`regexp`,`relativ`,`type` FROM grupper
            """)

    def get_group_members(self, group_id):
        return self._fetchall("""
            SELECT `personid` FROM `gruppemedlemmer`
            WHERE `gruppeid`='%s'
            """, group_id, column=0)

    def get_grad_group_members(self, group_id, grad):
        return self._fetchall("""
            SELECT `personid` FROM `gradgruppemedlemmer`
            WHERE `gruppeid`='%s' AND `grad`='%s'
            """, group_id, grad, column=0)

    def get_user_by_title(self, title, grad):
        return self._fetchall("""
            SELECT `personid` FROM `titler`
            WHERE `inttitel`='%s' AND `grad`='%s'
            """, title, grad, column=0)

    def get_user_by_id(self, user_id):
        return self._fetchall("""
            SELECT `id` FROM `tkfolk`
            WHERE `id`='%s'
            """, user_id, column=0)
