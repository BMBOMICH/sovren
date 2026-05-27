import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions,
    TransportKind,
} from 'vscode-languageclient/node';

let client: LanguageClient | undefined;
let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext) {
    outputChannel = vscode.window.createOutputChannel('Sovereign');
    outputChannel.appendLine('Sovereign extension activating...');

    // Start LSP
    const config = vscode.workspace.getConfiguration('sovereign');
    if (config.get<boolean>('enableLSP', true)) {
        startLanguageServer(context);
    }

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('sovereign.build', () => buildFile(false)),
        vscode.commands.registerCommand('sovereign.buildRelease', () => buildFile(true)),
        vscode.commands.registerCommand('sovereign.runTests', () => runTests()),
        vscode.commands.registerCommand('sovereign.check', () => checkFile()),
        vscode.commands.registerCommand('sovereign.format', () => formatFile()),
        vscode.commands.registerCommand('sovereign.newProject', () => newProject()),
    );

    // Format on save
    context.subscriptions.push(
        vscode.workspace.onWillSaveTextDocument(e => {
            if (e.document.languageId === 'sovereign') {
                const config = vscode.workspace.getConfiguration('sovereign');
                if (config.get<boolean>('formatOnSave', true)) {
                    e.waitUntil(
                        vscode.commands.executeCommand('editor.action.formatDocument')
                    );
                }
            }
        })
    );

    // Status bar
    const statusBar = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left, 100
    );
    statusBar.text = '$(triangle-right) Sovereign';
    statusBar.command = 'sovereign.build';
    statusBar.tooltip = 'Click to build (Ctrl+Shift+B)';
    context.subscriptions.push(statusBar);

    vscode.window.onDidChangeActiveTextEditor(editor => {
        if (editor?.document.languageId === 'sovereign') {
            statusBar.show();
        } else {
            statusBar.hide();
        }
    });

    if (vscode.window.activeTextEditor?.document.languageId === 'sovereign') {
        statusBar.show();
    }

    outputChannel.appendLine('Sovereign extension activated.');
}

function getSovereignBin(): string {
    const config = vscode.workspace.getConfiguration('sovereign');
    return config.get<string>('serverPath', 'sovereign');
}

function getCurrentFile(): string | undefined {
    return vscode.window.activeTextEditor?.document.fileName;
}

function buildFile(release: boolean) {
    const file = getCurrentFile();
    if (!file || !file.endsWith('.sov')) {
        vscode.window.showErrorMessage('Open a .sov file to build');
        return;
    }

    const sov = getSovereignBin();
    const args = ['build', file];
    if (release) args.push('--size');

    outputChannel.show();
    outputChannel.appendLine(`\n▶ Building ${path.basename(file)}...`);

    const terminal = vscode.window.createTerminal({
        name: 'Sovereign Build',
        cwd: path.dirname(file),
    });
    terminal.show();
    terminal.sendText(`${sov} ${args.join(' ')}`);
}

function runTests() {
    const file = getCurrentFile();
    if (!file || !file.endsWith('.sov')) {
        vscode.window.showErrorMessage('Open a .sov file to test');
        return;
    }

    const terminal = vscode.window.createTerminal({
        name: 'Sovereign Tests',
        cwd: path.dirname(file),
    });
    terminal.show();
    terminal.sendText(`${getSovereignBin()} test ${file}`);
}

async function checkFile() {
    const file = getCurrentFile();
    if (!file || !file.endsWith('.sov')) { return; }

    const { exec } = require('child_process');
    const sov = getSovereignBin();

    exec(`${sov} check "${file}"`, (err: any, stdout: string, stderr: string) => {
        const output = stdout + stderr;
        if (output.includes('No errors')) {
            vscode.window.showInformationMessage('✅ No errors found');
        } else {
            outputChannel.show();
            outputChannel.appendLine(output);
            vscode.window.showErrorMessage('Type errors found — see output');
        }
    });
}

async function formatFile() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== 'sovereign') { return; }

    const file = editor.document.fileName;
    const { exec } = require('child_process');
    const sov = getSovereignBin();

    // Save first
    await editor.document.save();

    exec(`${sov} fmt "${file}"`, (err: any) => {
        if (!err) {
            // Reload the document
            vscode.commands.executeCommand('workbench.action.revertFile');
        }
    });
}

async function newProject() {
    const name = await vscode.window.showInputBox({
        prompt: 'Project name',
        placeHolder: 'my-sovereign-app',
    });
    if (!name) { return; }

    const uri = await vscode.window.showOpenDialog({
        canSelectFolders: true,
        canSelectMany: false,
        openLabel: 'Select project location',
    });
    if (!uri || uri.length === 0) { return; }

    const projectDir = path.join(uri[0].fsPath, name);
    fs.mkdirSync(projectDir, { recursive: true });
    fs.mkdirSync(path.join(projectDir, 'src'), { recursive: true });

    fs.writeFileSync(
        path.join(projectDir, 'sovereign.toml'),
        `[package]\nname = "${name}"\nversion = "0.1.0"\n`
    );

    fs.writeFileSync(
        path.join(projectDir, 'src', 'main.sov'),
        `/// ${name} — built with Sovereign\n\nprint "Hello from ${name}!"\n`
    );

    const doc = await vscode.workspace.openTextDocument(
        path.join(projectDir, 'src', 'main.sov')
    );
    await vscode.window.showTextDocument(doc);
    vscode.window.showInformationMessage(
        `✅ Created '${name}'. Run: sovereign pkg build`
    );
}

function startLanguageServer(context: vscode.ExtensionContext) {
    const sov = getSovereignBin();

    const serverOptions: ServerOptions = {
        run:   { command: sov, args: ['lsp'], transport: TransportKind.stdio },
        debug: { command: sov, args: ['lsp'], transport: TransportKind.stdio },
    };

    const clientOptions: LanguageClientOptions = {
        documentSelector: [{ scheme: 'file', language: 'sovereign' }],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.sov'),
        },
        outputChannel,
    };

    client = new LanguageClient(
        'sovereign-lsp',
        'Sovereign Language Server',
        serverOptions,
        clientOptions,
    );

    client.start();
    context.subscriptions.push(client);
    outputChannel.appendLine('Language server started.');
}

export function deactivate(): Thenable<void> | undefined {
    return client?.stop();
}