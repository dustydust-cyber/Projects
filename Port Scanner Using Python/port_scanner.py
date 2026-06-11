#!/usr/bin/env python3

"""
Advanced Multi-threaded Port Scanner with GUI
Features: Multi-threading, Banner Grabbing, Service Detection, Hostname Resolution, and CSV/PDF Export.
"""

import socket
import sys
import threading
import csv
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Extended Common ports mapping for service detection
COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS", 993: "IMAPS",
    995: "POP3S", 1433: "MSSQL", 3306: "MySQL", 3389: "RDP",
    5432: "PostgreSQL", 8080: "HTTP-Proxy", 8443: "HTTPS-Alt",
    # Google Cloud & Cloud Services
    5672: "RabbitMQ", 6379: "Redis", 7199: "GCP-Monitoring", 9200: "Elasticsearch",
    9300: "Elasticsearch-Cluster", 11211: "Memcached", 27017: "MongoDB", 27018: "MongoDB-Replica",
    27019: "MongoDB-Config", 27020: "MongoDB-Shard", 5985: "WinRM-HTTP", 5986: "WinRM-HTTPS"
}

class PortScannerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced Network Port Scanner")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)
        self.scan_results = []
        self.is_scanning = False
        
        self.setup_ui()

    def setup_ui(self):
        # --- Top Input Panel ---
        input_frame = ttk.LabelFrame(self.root, text=" Scan Configurations ", padding=10)
        input_frame.pack(fill="x", padx=15, pady=10, side="top")
        
        ttk.Label(input_frame, text="Target IP / Hostname:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.target_entry = ttk.Entry(input_frame, width=30)
        self.target_entry.insert(0, "127.0.0.1")
        self.target_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(input_frame, text="Scan Mode:").grid(row=0, column=2, sticky="w", padx=20, pady=5)
        self.scan_mode = tk.StringVar(value="common")
        
        mode_frame = ttk.Frame(input_frame)
        mode_frame.grid(row=0, column=3, sticky="w")
        ttk.Radiobutton(mode_frame, text="Common Ports", variable=self.scan_mode, value="common", command=self.toggle_port_inputs).pack(side="left", padx=5)
        ttk.Radiobutton(mode_frame, text="Custom Range", variable=self.scan_mode, value="range", command=self.toggle_port_inputs).pack(side="left", padx=5)
        
        # Custom Port Range Controls
        self.range_frame = ttk.Frame(input_frame)
        ttk.Label(self.range_frame, text="Start:").pack(side="left", padx=2)
        self.start_port = ttk.Entry(self.range_frame, width=6)
        self.start_port.insert(0, "1")
        self.start_port.pack(side="left", padx=2)
        
        ttk.Label(self.range_frame, text="End:").pack(side="left", padx=5)
        self.end_port = ttk.Entry(self.range_frame, width=6)
        self.end_port.insert(0, "1024")
        self.end_port.pack(side="left", padx=2)
        
        # Action Buttons
        btn_frame = ttk.Frame(input_frame)
        btn_frame.grid(row=1, column=0, columnspan=4, pady=10)
        
        self.scan_btn = ttk.Button(btn_frame, text="Start Scan", command=self.start_scan_thread, width=15)
        self.scan_btn.pack(side="left", padx=10)
        
        self.export_btn = ttk.Button(btn_frame, text="Export Report", command=self.show_export_menu, state="disabled", width=15)
        self.export_btn.pack(side="left", padx=10)
        
        # --- Progress Bar and Status ---
        progress_frame = ttk.Frame(self.root, padding=5)
        progress_frame.pack(fill="x", padx=15)
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(fill="x", side="top", pady=2)
        
        self.status_label = ttk.Label(progress_frame, text="Ready", font=("Helvetica", 9, "italic"))
        self.status_label.pack(side="left")
        
        # --- Results Table ---
        table_frame = ttk.Frame(self.root, padding=15)
        table_frame.pack(fill="both", expand=True)
        
        columns = ("port", "status", "service", "banner")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        
        self.tree.heading("port", text="Port")
        self.tree.heading("status", text="Status")
        self.tree.heading("service", text="Detected Service")
        self.tree.heading("banner", text="Banner / Details")
        
        self.tree.column("port", width=80, anchor="center")
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("service", width=150, anchor="w")
        self.tree.column("banner", width=400, anchor="w")
        
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Add visual tag styling for Open/Closed ports
        self.tree.tag_configure("open", foreground="green", font=("Helvetica", 9, "bold"))
        self.tree.tag_configure("closed", foreground="gray")

    def toggle_port_inputs(self):
        if self.scan_mode.get() == "range":
            self.range_frame.grid(row=0, column=4, padx=10, sticky="w")
        else:
            self.range_frame.grid_forget()

    def grab_banner(self, sock, port):
        """Attempts to harvest software banners from common protocols"""
        try:
            # HTTP protocols need a basic requests payload to trigger a response
            if port in [80, 8080]:
                sock.sendall(b"HEAD / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            else:
                # Give a small poke for standard text banners (SSH, FTP, SMTP)
                sock.sendall(b"\r\n")
                
            banner = sock.recv(1024).decode('utf-8', errors='ignore').strip()
            # Clean up multi-line system logs or raw headers into a single readable line
            return banner.replace('\r', '').replace('\n', ' | ')[:100]
        except Exception:
            return "No banner responded"

    def scan_single_port(self, ip, port, lock):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            result = sock.connect_ex((ip, port))
            
            service = COMMON_PORTS.get(port, "Unknown")
            banner = "N/A"
            status = "CLOSED"
            
            if result == 0:
                status = "OPEN"
                banner = self.grab_banner(sock, port)
                
            sock.close()
            
            with lock:
                self.scan_results.append({"port": port, "status": status, "service": service, "banner": banner})
                self.root.after(0, self.update_ui_with_result, port, status, service, banner)
                
        except Exception:
            pass
        finally:
            with lock:
                self.ports_processed += 1
                self.root.after(0, self.update_progress)

    def update_ui_with_result(self, port, status, service, banner):
        tag = "open" if status == "OPEN" else "closed"
        if status == "OPEN" or self.scan_mode.get() == "range":
            self.tree.insert("", "end", values=(port, status, service, banner), tags=(tag,))

    def update_progress(self):
        progress_pct = (self.ports_processed / self.total_ports) * 100
        self.progress_bar["value"] = progress_pct
        self.status_label.config(text=f"Scanning... {self.ports_processed}/{self.total_ports} ports processed.")
        
        if self.ports_processed >= self.total_ports:
            self.finalize_scan()

    def start_scan_thread(self):
        if self.is_scanning:
            return
            
        target_input = self.target_entry.get().strip()
        if not target_input:
            messagebox.showerror("Error", "Please specify a target IP or domain.")
            return

        # Hostname Resolution
        self.status_label.config(text="Resolving target host...")
        try:
            self.target_ip = socket.gethostbyname(target_input)
            self.resolved_hostname = target_input
        except socket.gaierror:
            messagebox.showerror("Error", f"Failed to resolve host: {target_input}")
            self.status_label.config(text="Resolution failed.")
            return

        # Parse target ports
        if self.scan_mode.get() == "common":
            ports_to_scan = sorted(list(COMMON_PORTS.keys()))
        else:
            try:
                start = int(self.start_port.get())
                end = int(self.end_port.get())
                if not (1 <= start <= 65535 and 1 <= end <= 65535) or start > end:
                    raise ValueError
                ports_to_scan = list(range(start, end + 1))
            except ValueError:
                messagebox.showerror("Error", "Invalid custom port range configurations.")
                return

        # UI reset
        self.is_scanning = True
        self.scan_btn.config(state="disabled")
        self.export_btn.config(state="disabled")
        self.tree.delete(*self.tree.get_children())
        
        self.scan_results = []
        self.total_ports = len(ports_to_scan)
        self.ports_processed = 0
        self.progress_bar["value"] = 0
        
        # Fire off threading mechanism
        threading.Thread(target=self.run_threaded_scanner, args=(ports_to_scan,), daemon=True).start()

    def run_threaded_scanner(self, ports):
        lock = threading.Lock()
        threads = []
        
        # Max simultaneous worker pools to protect OS descriptors from exhaustion
        max_threads = 100 
        
        for port in ports:
            # Active wait loop if pool gets overly packed
            while threading.active_count() > max_threads:
                pass
                
            t = threading.Thread(target=self.scan_single_port, args=(self.target_ip, port, lock))
            threads.append(t)
            t.start()

    def finalize_scan(self):
        self.is_scanning = False
        self.scan_btn.config(state="normal")
        self.export_btn.config(state="normal")
        self.status_label.config(text=f"Scan complete for {self.target_ip}. Hostname: {self.resolved_hostname}")
        messagebox.showinfo("Success", "Port scanning workflow finished successfully.")

    def show_export_menu(self):
        popup = tk.Toplevel(self.root)
        popup.title("Export Options")
        popup.geometry("300x120")
        popup.resizable(False, False)
        popup.grab_set()
        
        ttk.Label(popup, text="Select format to save report:").pack(pady=10)
        
        btn_frame = ttk.Frame(popup)
        btn_frame.pack(pady=5)
        
        ttk.Button(btn_frame, text="CSV File", command=lambda: [popup.destroy(), self.export_csv()]).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="PDF Document", command=lambda: [popup.destroy(), self.export_pdf()]).pack(side="left", padx=10)

    def export_csv(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not file_path:
            return
            
        try:
            with open(file_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Target IP", "Target Host", "Timestamp"])
                writer.writerow([self.target_ip, self.resolved_hostname, datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
                writer.writerow([])
                writer.writerow(["Port", "Status", "Service", "Banner"])
                
                for res in sorted(self.scan_results, key=lambda x: x['port']):
                    writer.writerow([res['port'], res['status'], res['service'], res['banner']])
            messagebox.showinfo("Export Success", f"Report saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Could not create file: {str(e)}")

    def export_pdf(self):
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
        except ImportError:
            messagebox.showerror("Dependency Missing", "ReportLab module is required for PDF builds.\nRun: pip install reportlab")
            return
            
        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Documents", "*.pdf")])
        if not file_path:
            return
            
        try:
            doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            styles = getSampleStyleSheet()
            story = []
            
            # Title Formatting
            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=22, textColor=colors.HexColor("#1A365D"), spaceAfter=12)
            story.append(Paragraph("Network Audit: Port Scan Report", title_style))
            story.append(Spacer(1, 10))
            
            # Summary Metadata Metainfo Table
            meta_data = [
                [Paragraph("<b>Target IP Address:</b>", styles['Normal']), Paragraph(self.target_ip, styles['Normal'])],
                [Paragraph("<b>Resolved Host:</b>", styles['Normal']), Paragraph(self.resolved_hostname, styles['Normal'])],
                [Paragraph("<b>Execution Time:</b>", styles['Normal']), Paragraph(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), styles['Normal'])]
            ]
            meta_table = Table(meta_data, colWidths=[130, 400])
            meta_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
            story.append(meta_table)
            story.append(Spacer(1, 20))
            
            # Dynamic Results Compiled Data
            table_data = [[Paragraph("<b>Port</b>", styles['Normal']), Paragraph("<b>Status</b>", styles['Normal']), Paragraph("<b>Service</b>", styles['Normal']), Paragraph("<b>Banner / Context Details</b>", styles['Normal'])]]
            
            sorted_results = sorted(self.scan_results, key=lambda x: x['port'])
            for res in sorted_results:
                # Highlight Open rows slightly for quick document reading
                status_color = "<font color='green'><b>OPEN</b></font>" if res['status'] == "OPEN" else "<font color='gray'>CLOSED</font>"
                
                table_data.append([
                    Paragraph(str(res['port']), styles['Normal']),
                    Paragraph(status_color, styles['Normal']),
                    Paragraph(res['service'], styles['Normal']),
                    Paragraph(res['banner'], styles['Normal'])
                ])
                
            results_table = Table(table_data, colWidths=[50, 60, 100, 330], repeatRows=1)
            results_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            
            story.append(results_table)
            doc.build(story)
            messagebox.showinfo("Export Success", f"PDF Report constructed at:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed compiling PDF payload: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = PortScannerGUI(root)
    root.mainloop()