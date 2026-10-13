Quero implementar uma segunda visualização 3D das estruturas a partir do scf.

Quero que no menu do botão direito do mouse tenha seja adicionado a opção "Abrir com XCrysDen". Onde abre o arquivo com o xcrysden usando '--pwi', por exemplo 'xcrysden --pwi scf.in'

- O caminho de instalação do xcrysden deve ser lido do arquivo 'config.yaml' na chave 'xcrysden_path'.

- Se o 'xcrysden_path' estiver vazio, então a opção "Abrir com XCrysDen" deve ser desabilitada.

- O "Abrir com XCrysDen" só deve aparecer se o arquivo for um arquivo '.in' ou '.out' do pw.x
