import unittest
import database
import test_web


class AdminTests(unittest.TestCase):
    def setUp(self):
        test_web.WebTests.setUp(self)

    def login(self, client, username):
        return client.post('/login',data={'usuario':username,'password':'test'})

    def test_admin_creates_area_and_assigns_user_roles(self):
        self.login(self.client,'admin')
        self.assertEqual(self.client.post('/admin/areas/crear',data={'nombre_area':'CALIDAD'}).status_code,302)
        response=self.client.post('/admin/usuarios/crear',data={'usuario':'calidad','password':'test','nombre':'Coordinador','rol':'coordinador','area':'CALIDAD'})
        self.assertEqual(response.status_code,302)
        user=database.read_catalog('usuarios')['calidad']
        self.assertEqual((user['rol'],user['area']),('coordinador','CALIDAD'))
        self.client.post('/admin/usuarios/crear',data={'usuario':'rh','password':'test','rol':'rrhh','area':'CALIDAD'})
        self.assertEqual(database.read_catalog('usuarios')['rh']['area'],'TODAS')
        response=self.client.post('/admin/usuarios/crear',data={'usuario':'invalid','password':'test','rol':'coordinador','area':'DESCONOCIDA'})
        self.assertEqual(response.status_code,400)
        self.assertNotIn('invalid',database.read_catalog('usuarios'))

    def test_non_admin_cannot_grant_permissions(self):
        users=database.read_catalog('usuarios')
        users['rh']={'pass':'test','nombre':'RH','rol':'rrhh','area':'TODAS'}
        database.write_catalog('usuarios',users)
        for username in ('jefe','rh'):
            client=self.app.test_client()
            self.login(client,username)
            before=database.read_catalog('usuarios')
            client.post('/admin/usuarios/crear',data={'usuario':'intruso','password':'test','rol':'admin'})
            client.post('/admin/usuarios/editar/'+username,data={'rol':'admin','area':'TODAS'})
            self.assertEqual(database.read_catalog('usuarios'),before)
            client.post('/admin/areas/crear',data={'nombre_area':'INTRUSA'})
            self.assertNotIn('INTRUSA',database.read_catalog('areas'))

    def test_permission_changes_apply_to_open_session(self):
        self.login(self.client,'admin')
        employee_client=self.app.test_client()
        self.login(employee_client,'jefe')
        self.assertEqual(employee_client.get('/').status_code,200)
        self.client.post('/admin/usuarios/editar/jefe',data={'rol':'rrhh','area':'TODAS'})
        self.assertEqual(employee_client.get('/').status_code,403)
        self.assertEqual(employee_client.get('/colaboradores').status_code,200)
        self.client.post('/admin/usuarios/eliminar/jefe')
        response=employee_client.get('/colaboradores')
        self.assertEqual(response.status_code,302)
        self.assertTrue(response.location.endswith('/login'))


if __name__=='__main__': unittest.main()
