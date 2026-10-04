"""Subset of DMTF SMBIOS types 0/1/2/3/4/16/17, decoded from the Linux DMI table.

Reads bytes only; never reads /dev/mem or probes I2C/SPD. Offsets and enumeration
values follow the DMTF DSP0134 specification. Truncated tables are rejected.
"""
import uuid
MEMORY_TYPES={0x03:'DRAM',0x0f:'SDRAM',0x12:'DDR',0x13:'DDR2',0x18:'DDR3',0x1a:'DDR4',0x1b:'LPDDR',0x1c:'LPDDR2',0x1d:'LPDDR3',0x1e:'LPDDR4',0x22:'DDR5',0x23:'LPDDR5',0x24:'HBM3'}
FORM_FACTORS={5:'Chip',9:'DIMM',11:'Row Of Chips',13:'SODIMM',15:'FB-DIMM',16:'Die'}
CHASSIS={3:'Desktop',8:'Portable',9:'Laptop',10:'Notebook',13:'All-in-one',14:'Sub-notebook',23:'Rack server',30:'Tablet',31:'Convertible',32:'Detachable',35:'Mini PC'}

def parse_smbios(blob):
    if not isinstance(blob,bytes) or len(blob)<4:raise ValueError('Firmware table is empty or invalid')
    if len(blob)>16*1024**2:raise ValueError('Firmware table exceeds the supported size')
    sections=[];pos=0
    while pos+4<=len(blob):
        typ,length=blob[pos],blob[pos+1]
        if length<4 or pos+length>len(blob):raise ValueError('Truncated firmware structure')
        end=blob.find(b'\0\0',pos+length)
        if end<0:raise ValueError('Unterminated firmware strings')
        data=blob[pos:pos+length]
        strings=[s.decode('utf-8',errors='replace').strip() for s in blob[pos+length:end].split(b'\0')]
        def integer(offset,width=1):
            return int.from_bytes(data[offset:offset+width],'little') if offset+width<=length else None
        def string(offset):
            index=integer(offset)
            return strings[index-1] if index is not None and 0<index<=len(strings) else None
        fields={}
        mapping={0:{4:'Vendor',5:'Version',8:'Release Date'},1:{4:'Manufacturer',5:'Product Name',6:'Version',7:'Serial Number',0x19:'SKU Number',0x1a:'Family'},
            2:{4:'Manufacturer',5:'Product Name',6:'Version',7:'Serial Number'},3:{4:'Manufacturer',6:'Version',7:'Serial Number'},4:{7:'Manufacturer',0x10:'Version'}}
        for offset,label in mapping.get(typ,{}).items():
            value=string(offset)
            if value:fields[label]=value
        if typ==0:
            major,minor=integer(0x14),integer(0x15)
            if major is not None and minor is not None and major!=255 and minor!=255:fields['BIOS Revision']=f'{major}.{minor}'
        elif typ==1 and length>=24:
            raw=data[8:24]
            if raw not in (b'\0'*16,b'\xff'*16):fields['UUID']=str(uuid.UUID(bytes_le=raw))
        elif typ==3:
            code=integer(5)
            if code is not None:fields['Type']=CHASSIS.get(code&0x7f,f'Chassis type {code&0x7f}')
        elif typ==4:
            for offset,label in [(0x14,'Max Speed'),(0x16,'Current Speed')]:
                value=integer(offset,2)
                if value:fields[label]=f'{value} MHz'
        elif typ==16 and length>=0x0f:
            fields['Number Of Devices']=str(integer(0x0d,2))
            fields['Use']='System Memory' if integer(5)==3 else 'Other memory array'
        elif typ==17 and length>=0x15:
            fields['Array Handle']=f'0x{integer(4,2):04x}'
            size=integer(0x0c,2)
            if size==0:fields['Size']='No Module Installed'
            elif size==0xffff:fields['Size']='Unknown'
            elif size==0x7fff:
                extended=integer(0x1c,4)
                fields['Size']=f'{extended&0x7fffffff} MB' if extended is not None else 'Unknown'
            elif size&0x8000:fields['Size']=f'{size&0x7fff} kB'
            else:fields['Size']=f'{size} MB'
            fields['Form Factor']=FORM_FACTORS.get(integer(0x0e),'Unknown')
            fields['Type']=MEMORY_TYPES.get(integer(0x12),'Unknown')
            for offset,label in [(0x10,'Locator'),(0x11,'Bank Locator'),(0x17,'Manufacturer'),(0x18,'Serial Number'),(0x1a,'Part Number')]:
                value=string(offset)
                if value:fields[label]=value
            for offset,label in [(0x08,'Total Width'),(0x0a,'Data Width')]:
                value=integer(offset,2)
                if value not in (None,0,0xffff):fields[label]=f'{value} bits'
            for offset,extended,label in [(0x15,0x54,'Speed'),(0x20,0x58,'Configured Memory Speed')]:
                value=integer(offset,2)
                if value==0xffff:value=integer(extended,4)
                if value:fields[label]=f'{value} MT/s'
            rank=integer(0x1b)
            if rank is not None and rank&0xf:fields['Rank']=str(rank&0xf)
            voltage=integer(0x26,2)
            if voltage:fields['Configured Voltage']=f'{voltage/1000:.3f} V'
        if typ in (0,1,2,3,4,16,17):sections.append({'type':typ,'handle':f'0x{integer(2,2):04x}','fields':fields})
        pos=end+2
        if typ==127:break
    if not sections:raise ValueError('No supported firmware inventory structures were found')
    return sections
