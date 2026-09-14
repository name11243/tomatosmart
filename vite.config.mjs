import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
export default defineConfig({plugins:[vue()],build:{outDir:'dist/client'},server:{host:'127.0.0.1',allowedHosts:['terminal.local'],proxy:{'/api':'http://127.0.0.1:8016'}}});
